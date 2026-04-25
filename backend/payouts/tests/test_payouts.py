"""
Concurrency and idempotency tests for the Payout Engine.

These are the two mandatory tests from the challenge spec.

test_concurrent_payouts_one_succeeds:
    Sends 10 simultaneous payout requests of 60 rupees each for a merchant
    with exactly 100 rupees available. Due to SELECT FOR UPDATE locking,
    exactly 1 should succeed and 9 should be rejected with 402.
    This proves we have no race condition on the check-then-deduct path.

test_idempotency_same_key_no_duplicate:
    Sends the same payout request twice with the same Idempotency-Key UUID.
    Only 1 Payout row should be created. Both responses must be identical.
    This proves the idempotency layer works correctly.

test_idempotency_different_merchant_same_key:
    Proves that idempotency keys are scoped per merchant — the same key UUID
    used by two different merchants should create two independent payouts.

test_state_machine_blocks_illegal_transitions:
    Directly tests that the state machine rejects terminal → active transitions.

test_failed_payout_refunds_funds:
    Tests that marking a payout as failed atomically restores the merchant balance.
"""

import uuid
import threading
import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from merchants.models import Merchant
from ledger.models import LedgerEntry, EntryType
from ledger.queries import get_merchant_balance
from payouts.models import Payout, PayoutStatus
from payouts.state_machine import assert_legal_transition, InvalidStateTransitionError
from payouts.services import (
    create_payout_atomic,
    mark_payout_failed,
    InsufficientFundsError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def merchant(db):
    """Creates a merchant with 100 rupees (10,000 paise) available balance."""
    user = User.objects.create_user(username="test_merchant", password="pass")
    m = Merchant.objects.create(
        user=user,
        name="Test Merchant",
        email="test@merchant.com",
        bank_account_id="TEST_BANK_001",
    )
    # Seed 100 rupees (10,000 paise) as a credit
    LedgerEntry.objects.create(
        merchant=m,
        amount_paise=10_000,
        entry_type=EntryType.CREDIT,
        description="Initial test credit",
    )
    return m


@pytest.fixture
def merchant2(db):
    """A second merchant with 10,000 paise."""
    user = User.objects.create_user(username="test_merchant2", password="pass")
    m = Merchant.objects.create(
        user=user,
        name="Test Merchant 2",
        email="test2@merchant.com",
        bank_account_id="TEST_BANK_002",
    )
    LedgerEntry.objects.create(
        merchant=m,
        amount_paise=10_000,
        entry_type=EntryType.CREDIT,
        description="Initial test credit for merchant 2",
    )
    return m


@pytest.fixture
def auth_client(merchant):
    """DRF test client authenticated as merchant."""
    token = Token.objects.create(user=merchant.user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.fixture
def auth_client2(merchant2):
    token = Token.objects.create(user=merchant2.user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


# ---------------------------------------------------------------------------
# Test 1: Concurrency — exactly one of N concurrent payouts must succeed
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_concurrent_payouts_one_succeeds(merchant):
    """
    10 threads simultaneously request a 60 rupee (6,000 paise) payout
    for a merchant with exactly 100 rupees (10,000 paise).

    Expected: exactly 1 succeeds (HTTP 201), 9 fail with InsufficientFundsError.
    This tests the SELECT FOR UPDATE lock in services.create_payout_atomic().

    If the lock were absent, multiple threads could pass the balance check
    before any debit is written — leading to overdraft.
    """
    AMOUNT = 6_000  # 60 rupees — each request would exhaust the balance alone
    NUM_THREADS = 10

    results = []
    errors = []
    results_lock = threading.Lock()

    def attempt_payout():
        try:
            from payouts.models import IdempotencyKey
            # Each thread uses a unique idempotency key
            idem_key = IdempotencyKey.objects.create(
                key=uuid.uuid4(),
                merchant=merchant,
                response_status=None,
                response_body=None,
            )
            payout = create_payout_atomic(
                merchant=merchant,
                amount_paise=AMOUNT,
                bank_account_id="TEST_BANK_001",
                idempotency_key_obj=idem_key,
            )
            with results_lock:
                results.append(("success", payout.id))
        except InsufficientFundsError as e:
            with results_lock:
                results.append(("insufficient_funds", str(e)))
        except Exception as e:
            with results_lock:
                errors.append(str(e))

    threads = [threading.Thread(target=attempt_payout) for _ in range(NUM_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Assert: no unexpected errors
    assert errors == [], f"Unexpected errors during concurrent test: {errors}"

    successes = [r for r in results if r[0] == "success"]
    failures = [r for r in results if r[0] == "insufficient_funds"]

    # Exactly one request should have succeeded
    assert len(successes) == 1, (
        f"Expected exactly 1 success, got {len(successes)}. "
        f"This means the SELECT FOR UPDATE lock is NOT working — race condition exists."
    )
    assert len(failures) == NUM_THREADS - 1, (
        f"Expected {NUM_THREADS - 1} failures, got {len(failures)}."
    )

    # Verify ledger integrity: balance should be 4,000 paise (100 rupees - 60 rupees)
    balance = get_merchant_balance(merchant)
    # Note: the successful payout is in 'pending' state, so the DEBIT is held
    # available = 10000 - 6000 (debit) = 4000
    assert balance["available"] == 4_000, (
        f"Balance integrity failure. Expected 4000p available, got {balance['available']}p. "
        f"Sum of credits minus debits must always equal the displayed balance."
    )

    # Verify only 1 Payout row was created
    payout_count = Payout.objects.filter(merchant=merchant).count()
    assert payout_count == 1, f"Expected 1 Payout row, found {payout_count}. Duplicate payout created!"


# ---------------------------------------------------------------------------
# Test 2: Idempotency — same key, no duplicate payout
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_idempotency_same_key_no_duplicate(auth_client, merchant):
    """
    Sending the same POST /api/v1/payouts/ request twice with the same
    Idempotency-Key UUID must:
      1. Create exactly 1 Payout row (no duplicate).
      2. Return identical responses for both requests.

    This simulates network retry — the client doesn't know if the first
    request succeeded, so it resends. We must not double-charge.
    """
    key = str(uuid.uuid4())
    payload = {
        "amount_paise": 1_000,  # 10 rupees
        "bank_account_id": "TEST_BANK_001",
    }

    # First request
    response1 = auth_client.post(
        "/api/v1/payouts/",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert response1.status_code == 201, f"First request failed: {response1.data}"

    # Second request with the same key
    response2 = auth_client.post(
        "/api/v1/payouts/",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert response2.status_code == 201, f"Second request failed: {response2.data}"

    # Responses must be identical
    assert response1.data == response2.data, (
        f"Idempotency failure: responses differ.\n"
        f"First:  {response1.data}\n"
        f"Second: {response2.data}"
    )

    # Exactly 1 Payout row must exist
    payout_count = Payout.objects.filter(merchant=merchant).count()
    assert payout_count == 1, (
        f"Idempotency failure: {payout_count} payout rows created. Expected 1."
    )


@pytest.mark.django_db(transaction=True)
def test_idempotency_key_scoped_per_merchant(auth_client, auth_client2, merchant, merchant2):
    """
    The same idempotency key UUID used by two different merchants should
    create two separate, independent payouts. Keys are scoped to (key, merchant).
    """
    key = str(uuid.uuid4())  # Same key UUID for both
    payload = {"amount_paise": 1_000, "bank_account_id": "BANK"}

    r1 = auth_client.post("/api/v1/payouts/", data=payload, format="json", HTTP_IDEMPOTENCY_KEY=key)
    r2 = auth_client2.post("/api/v1/payouts/", data=payload, format="json", HTTP_IDEMPOTENCY_KEY=key)

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.data["id"] != r2.data["id"], "Two merchants with the same key must get separate payouts."

    assert Payout.objects.filter(merchant=merchant).count() == 1
    assert Payout.objects.filter(merchant=merchant2).count() == 1


# ---------------------------------------------------------------------------
# Test 3: State machine — illegal transitions are blocked
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_state_machine_blocks_failed_to_completed(merchant):
    """
    Once a payout is FAILED, it cannot be moved to COMPLETED.
    The state machine must raise InvalidStateTransitionError.
    """
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        assert_legal_transition(PayoutStatus.FAILED, PayoutStatus.COMPLETED)

    assert "failed" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_state_machine_blocks_completed_to_pending(merchant):
    """Completed payouts cannot go back to any non-terminal state."""
    with pytest.raises(InvalidStateTransitionError):
        assert_legal_transition(PayoutStatus.COMPLETED, PayoutStatus.PENDING)


@pytest.mark.django_db
def test_state_machine_allows_legal_transitions():
    """Verify the happy path transitions are allowed."""
    # Should not raise
    assert_legal_transition(PayoutStatus.PENDING, PayoutStatus.PROCESSING)
    assert_legal_transition(PayoutStatus.PROCESSING, PayoutStatus.COMPLETED)
    assert_legal_transition(PayoutStatus.PROCESSING, PayoutStatus.FAILED)


# ---------------------------------------------------------------------------
# Test 4: Failed payout atomically refunds funds
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_failed_payout_refunds_funds_atomically(merchant):
    """
    When a payout transitions to FAILED, the held funds must be returned
    to the merchant balance via a compensating CREDIT entry.

    Both the state change and the refund happen in the same transaction.
    After failure: balance returns to original value.
    """
    from payouts.models import IdempotencyKey
    from payouts.services import mark_payout_processing

    initial_balance = get_merchant_balance(merchant)["available"]
    assert initial_balance == 10_000

    idem_key = IdempotencyKey.objects.create(key=uuid.uuid4(), merchant=merchant)
    payout = create_payout_atomic(
        merchant=merchant,
        amount_paise=5_000,  # 50 rupees
        bank_account_id="TEST_BANK",
        idempotency_key_obj=idem_key,
    )

    # Balance is now 5,000 (held 5,000 as a pending debit)
    balance_after_hold = get_merchant_balance(merchant)["available"]
    assert balance_after_hold == 5_000

    # Move to processing
    mark_payout_processing(str(payout.id))

    # Now fail it
    mark_payout_failed(str(payout.id), reason="Bank rejected transfer.")

    # Balance must be fully restored
    balance_after_failure = get_merchant_balance(merchant)["available"]
    assert balance_after_failure == 10_000, (
        f"Funds not restored after failure! Got {balance_after_failure}p, expected 10000p."
    )

    # Payout must be in FAILED state
    payout.refresh_from_db()
    assert payout.status == PayoutStatus.FAILED


# ---------------------------------------------------------------------------
# Test 5: Insufficient funds returns 402
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_insufficient_funds_rejected(auth_client, merchant):
    """
    Requesting more than the available balance returns 402.
    No payout row is created, no ledger entry is written.
    """
    payload = {
        "amount_paise": 999_999_999,  # Way more than available
        "bank_account_id": "TEST_BANK",
    }
    response = auth_client.post(
        "/api/v1/payouts/",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )
    assert response.status_code == 402
    assert Payout.objects.filter(merchant=merchant).count() == 0

    # Balance must be unchanged
    balance = get_merchant_balance(merchant)["available"]
    assert balance == 10_000
