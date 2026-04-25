# EXPLAINER.md — Playto Payout Engine

---

## 1. The Ledger

### The balance calculation query

```python
# ledger/queries.py — get_merchant_balance()
result = LedgerEntry.objects.filter(merchant=merchant).aggregate(
    available=Coalesce(
        Sum(Case(When(entry_type=EntryType.CREDIT, then="amount_paise"), default=Value(0), output_field=BigIntegerField()))
        - Sum(Case(When(entry_type=EntryType.DEBIT, then="amount_paise"), default=Value(0), output_field=BigIntegerField())),
        Value(0),
        output_field=BigIntegerField(),
    )
)
```

The raw SQL Django generates:

```sql
SELECT COALESCE(
    SUM(CASE WHEN entry_type = 'CREDIT' THEN amount_paise ELSE 0 END)
  - SUM(CASE WHEN entry_type = 'DEBIT'  THEN amount_paise ELSE 0 END),
  0
)
FROM ledger_entries
WHERE merchant_id = <id>;
```

**Why I modelled it this way:**

Credits and debits are immutable append-only rows rather than a single `balance` column on the `Merchant` table. This was a deliberate choice for three reasons:

1. **Auditability**: Every balance change has a row with a timestamp, description, and a `reference_id` linking it back to the specific payout. You can reconstruct the full ledger history at any point in time with no additional tables. This is non-negotiable in a money-moving system.

2. **Reversal semantics**: When a payout fails, the refund is a new `CREDIT` row written atomically in the same transaction as the `FAILED` status transition. There is no `UPDATE` that could lose money if interrupted. The ledger is append-only — nothing is ever modified or deleted.

3. **Correctness under concurrency**: A `balance` column would require an `UPDATE merchants SET balance = balance - %s WHERE id = %s` (which is fine but adds drift risk) *and* a separate check for sufficiency. The ledger model lets the balance check and the debit happen in the same `SELECT FOR UPDATE` + `INSERT` pattern with no UPDATE on a shared column.

**Why I did not use a balance column:**

A stored balance column is a denormalization. It creates two sources of truth that can drift. If a deployment bug, migration mishap, or unhandled exception causes the column and the ledger to diverge, you have a production incident. Starting from ledger entries means there is only one source of truth by construction.

**`BigIntegerField` in paise, not `DecimalField`:**

`DecimalField` is safer than `FloatField` (no IEEE 754 rounding) but still requires choosing precision. `BigInteger` in the smallest currency unit (paise) is exact integer arithmetic at every layer — Python, ORM, PostgreSQL, JSON. ₹10 = 1000 paise = the integer `1000`. No precision decisions, no rounding errors, no surprises.

---

## 2. The Lock

### Exact code that prevents two concurrent payouts from overdrawing a balance

```python
# payouts/services.py — create_payout_atomic()

with transaction.atomic():
    # Step 1: Acquire a row-level exclusive lock on the merchant.
    # Any other transaction attempting SELECT FOR UPDATE on this merchant
    # will BLOCK here until this transaction commits or rolls back.
    merchant_locked = Merchant.objects.select_for_update().get(pk=merchant.pk)

    # Step 2: Compute available balance in SQL — inside the lock.
    # This sees all committed writes from prior transactions.
    balance_result = LedgerEntry.objects.filter(merchant=merchant_locked).aggregate(
        available=Coalesce(
            Sum(Case(When(entry_type=EntryType.CREDIT, then="amount_paise"), default=Value(0), output_field=BigIntegerField()))
            - Sum(Case(When(entry_type=EntryType.DEBIT, then="amount_paise"), default=Value(0), output_field=BigIntegerField())),
            Value(0), output_field=BigIntegerField(),
        )
    )
    available = balance_result["available"]

    # Step 3: Sufficiency check.
    if available < amount_paise:
        raise InsufficientFundsError(...)

    # Step 4: Create payout + DEBIT entry — both inside the same transaction.
    payout = Payout.objects.create(...)
    LedgerEntry.objects.create(entry_type=EntryType.DEBIT, ...)

# Transaction commits here, releasing the lock.
```

**The database primitive it relies on:**

`SELECT FOR UPDATE` in PostgreSQL. This acquires an exclusive row-level lock on the `merchants` row for the duration of the transaction. PostgreSQL guarantees that no other transaction can acquire a conflicting lock on the same row until this transaction commits or rolls back.

**Why `SELECT FOR UPDATE` on the Merchant row, not the LedgerEntry table?**

We need to serialize all payout requests *for a given merchant*, not globally. Locking by merchant ID means:
- Merchant A and Merchant B can create payouts simultaneously (no cross-merchant blocking).
- Two requests for Merchant A are serialized — exactly one gets through the balance check before the other sees the updated ledger.

**Why not Python-level locks (`threading.Lock`, Redis `SETNX`)?**

Python threading locks don't protect across process boundaries. A production Django deployment runs 4–8 Gunicorn workers (separate OS processes). A `threading.Lock` in Worker 1 has no effect on Worker 2. Redis locks are closer (cross-process) but introduce a distributed systems failure mode: if the Redis lock holder crashes before releasing, other workers deadlock. PostgreSQL row locks are released automatically when the connection closes, even on crash.

**The race condition this prevents:**

Without `SELECT FOR UPDATE`:
- T=0ms: Thread A reads balance = 10,000 paise. Check: 6,000 ≤ 10,000 ✓
- T=1ms: Thread B reads balance = 10,000 paise. Check: 6,000 ≤ 10,000 ✓  ← stale read
- T=2ms: Thread A writes DEBIT 6,000. Balance = 4,000.
- T=3ms: Thread B writes DEBIT 6,000. Balance = -2,000. 💸 Overdraft.

With `SELECT FOR UPDATE`:
- T=0ms: Thread A acquires lock, reads balance = 10,000 paise. Check passes. Writes DEBIT. Commits. Lock released.
- T=1ms: Thread B acquires lock (was blocked). Reads balance = 4,000 paise. Check fails: 6,000 > 4,000. Raises InsufficientFundsError. 

---

## 3. The Idempotency

### How the system knows it has seen a key before

The `IdempotencyKey` table has a `UNIQUE (key, merchant_id)` constraint. On every request:

1. The server parses and validates the `Idempotency-Key` UUID from the request header.
2. It attempts a `get_or_create` on `(key, merchant)`. The unique constraint ensures this is atomic — only one row can exist for a given `(key, merchant)` pair.
3. **If the row already exists and `response_body IS NOT NULL`**: a previous request completed. Return the cached `response_status` + `response_body` verbatim.
4. **If the row exists but `response_body IS NULL`**: a previous request is in-flight (created the row but hasn't written a response yet). Return `409 Conflict`.
5. **If the row did not exist** (was just created): proceed with the payout logic. On completion (success or expected failure like insufficient funds), write the response to `response_body`.

The response is cached on the `IdempotencyKey` row itself, so subsequent calls are a single `SELECT` with no business logic re-execution.

### What happens if the first request is in-flight when the second arrives?

The second request will find the `IdempotencyKey` row (because the first request created it) but `response_body` will be `NULL` (because the first request hasn't finished). The server returns `409 Conflict` with a message: *"A request with this Idempotency-Key is already in progress. Retry after a few seconds."*

This is intentional. The alternatives are:
- **Wait for the first to complete**: requires long-polling or blocking I/O, complex to implement safely.
- **Return the same response anyway**: impossible, we don't have one yet.
- **409 with retry-after**: clean, honest, and tells the client exactly what to do.

**Key scoping and expiry:**

Keys are scoped per merchant via the `UNIQUE (key, merchant_id)` constraint. The same UUID used by Merchant A and Merchant B creates two independent records. Keys expire after 24 hours — checked at lookup time via `is_expired()`. Expired keys are deleted and the request proceeds as new.

---

## 4. The State Machine

### Where `failed → completed` is blocked

In `payouts/state_machine.py`:

```python
LEGAL_TRANSITIONS: dict[str, list[str]] = {
    PayoutStatus.PENDING:    [PayoutStatus.PROCESSING],
    PayoutStatus.PROCESSING: [PayoutStatus.COMPLETED, PayoutStatus.FAILED],
    PayoutStatus.COMPLETED:  [],   # terminal — no outgoing transitions
    PayoutStatus.FAILED:     [],   # terminal — no outgoing transitions
}

def assert_legal_transition(current_status: str, new_status: str) -> None:
    allowed = LEGAL_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        raise InvalidStateTransitionError(
            f"Cannot transition from '{current_status}' to '{new_status}'. "
            f"Legal next states from '{current_status}': {allowed or ['none (terminal state)']}"
        )
```

`failed → completed` is blocked because `LEGAL_TRANSITIONS[PayoutStatus.FAILED]` is an empty list. `PayoutStatus.COMPLETED` is not in that list, so `assert_legal_transition("failed", "completed")` raises `InvalidStateTransitionError`.

This function is called inside `mark_payout_completed()` and `mark_payout_failed()` in `services.py`, *after* acquiring a `SELECT FOR UPDATE` lock on the payout row. The lock prevents two concurrent tasks from transitioning the same payout simultaneously.

The state machine is an explicit whitelist (legal transitions listed), not a blacklist (illegal transitions blocked). A whitelist is safer: any new status added to the enum is blocked by default until explicitly added to the map.

---

## 5. The AI Audit

### One specific example where AI wrote subtly wrong code

**What the AI generated** (initial draft of `services.py`):

```python
# AI's first attempt — WRONG
def create_payout_atomic(merchant, amount_paise, bank_account_id, idempotency_key_obj):
    with transaction.atomic():
        # Fetch all ledger entries to Python, sum in Python
        entries = LedgerEntry.objects.filter(merchant=merchant)
        credits = sum(e.amount_paise for e in entries if e.entry_type == "CREDIT")
        debits = sum(e.amount_paise for e in entries if e.entry_type == "DEBIT")
        available = credits - debits

        if available < amount_paise:
            raise InsufficientFundsError(...)

        payout = Payout.objects.create(...)
        LedgerEntry.objects.create(entry_type="DEBIT", ...)
```

**What I caught:**

Two problems, both critical:

1. **Python-level summation is wrong under concurrency.** `entries = LedgerEntry.objects.filter(merchant=merchant)` fetches a snapshot at a point in time. Between the `filter()` call and the `if available < amount_paise` check, another transaction could commit a DEBIT entry. The Python-side sum is stale. This is a classic TOCTOU (time-of-check to time-of-use) race condition. The `SELECT FOR UPDATE` on the Merchant row serializes the *entry point*, but if the balance computation happens before the lock is acquired and in Python, not SQL, the lock only protects the INSERT, not the CHECK. This is the exact bug the spec said to watch for: "Race conditions on check-then-deduct are the most common bug we see."

2. **No lock on the Merchant row.** The AI's version opened a `transaction.atomic()` block but never called `select_for_update()`. `transaction.atomic()` alone does not serialize concurrent transactions — it only provides atomicity (all-or-nothing). Without the lock, two concurrent requests can both pass the balance check on stale data and both succeed, creating an overdraft.

**What I replaced it with:**

```python
with transaction.atomic():
    # Lock FIRST — before any reads
    merchant_locked = Merchant.objects.select_for_update().get(pk=merchant.pk)

    # Compute balance IN SQL, inside the lock — single aggregate, no Python summation
    balance_result = LedgerEntry.objects.filter(merchant=merchant_locked).aggregate(
        available=Coalesce(
            Sum(Case(When(entry_type=EntryType.CREDIT, then="amount_paise"), default=Value(0), output_field=BigIntegerField()))
            - Sum(Case(When(entry_type=EntryType.DEBIT, then="amount_paise"), default=Value(0), output_field=BigIntegerField())),
            Value(0), output_field=BigIntegerField(),
        )
    )
    available = balance_result["available"]

    if available < amount_paise:
        raise InsufficientFundsError(...)

    payout = Payout.objects.create(...)
    LedgerEntry.objects.create(entry_type=EntryType.DEBIT, ...)
```

The fix: lock first, compute in SQL second, check third, write fourth. All four steps are inside a single transaction. No Python-level aggregation. The `SELECT FOR UPDATE` on the Merchant row is the serialization primitive — not the transaction boundary itself.

This is the difference between understanding locking and just knowing the API.
