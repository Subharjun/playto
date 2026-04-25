# Playto Payout Engine

A production-correct payout engine for Playto Pay. Merchants accumulate INR balances from international customer payments and can request payouts to their Indian bank accounts.

**Key design properties:**
- ✅ All balances stored as `BigInteger` in paise — no floats, no decimals
- ✅ `SELECT FOR UPDATE` database-level locking — concurrency-safe, no overdrafts
- ✅ Full idempotency with per-merchant key scoping and 24h expiry
- ✅ Strict state machine with explicit legal-transition whitelist
- ✅ Celery background processing with exponential backoff + stuck-payout reaper

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Django 5 + Django REST Framework |
| Database | PostgreSQL 16 |
| Task queue | Celery + Redis |
| Frontend | React 18 + Tailwind CSS 3 |
| Containerization | Docker + Docker Compose |

---

## Quick Start (Docker)

```bash
# Clone and start everything
git clone <repo-url>
cd founderoffice-code

# Start all services (DB, Redis, Django, Celery worker + beat, React)
docker-compose up --build

# The seed command runs automatically on backend startup.
# Check backend logs for API tokens:
docker-compose logs backend | grep Token
```

- **Dashboard**: http://localhost:3000
- **API**: http://localhost:8000/api/v1/
- **Admin**: http://localhost:8000/admin/ (no superuser by default — create one with `createsuperuser`)

---

## Manual Setup (without Docker)

### Prerequisites
- Python 3.12+
- PostgreSQL 16
- Redis 7

### Backend

```bash
# Create and activate virtualenv
python3 -m venv venv
source venv/bin/activate

# Install dependencies
cd backend
pip install -r requirements.txt

# Configure environment
export DB_NAME=playto_payout
export DB_USER=playto
export DB_PASSWORD=playto_secret
export DB_HOST=localhost
export CELERY_BROKER_URL=redis://localhost:6379/0
export CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Create the database
createdb playto_payout
# Or: psql -c "CREATE DATABASE playto_payout;"

# Run migrations
python manage.py migrate

# Seed merchants (creates 3 merchants with credit history + API tokens)
python manage.py seed

# Start Django dev server
python manage.py runserver

# In a separate terminal: start Celery worker
celery -A config worker --loglevel=info

# In a separate terminal: start Celery Beat (scheduler for stuck-payout reaper)
celery -A config beat --loglevel=info
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

---

## Getting Started (Merchants)

The application now features a complete Auth flow.

**To use the dashboard:**
1. Open http://localhost:3000
2. Click **"Sign Up"** to register a new merchant account.
3. You can immediately log in with your new credentials.
4. (Optional) Run the seed script `python manage.py seed` inside the backend container to populate 3 pre-configured merchants with transaction history.

*Note: For newly signed-up accounts, you will need to add funds manually via the Django shell to test payouts, or use the pre-seeded accounts.*

Each merchant gets a DRF Token. Use the token in the Authorization header:

```
Authorization: Token <token_value>
```

Or paste it into the dashboard login form.

To reset and re-seed:
```bash
python manage.py seed --reset
```

---

## API Reference

All endpoints require `Authorization: Token <token>`.

### `GET /api/v1/merchants/me/`
Returns the authenticated merchant's profile, available balance, and held balance.

```json
{
  "id": "uuid",
  "name": "Acme Exports Pvt Ltd",
  "email": "acme@example.com",
  "bank_account_id": "ICICI_9876543210",
  "available_balance_paise": 10500,
  "held_balance_paise": 0,
  "created_at": "2025-04-25T03:00:00Z"
}
```

### `POST /api/v1/payouts/`

**Required header**: `Idempotency-Key: <UUID>`

**Body**:
```json
{
  "amount_paise": 5000,
  "bank_account_id": "ICICI_9876543210"
}
```

**Responses**:
- `201 Created` — payout created, processing queued
- `400 Bad Request` — validation error
- `402 Payment Required` — insufficient funds
- `409 Conflict` — duplicate idempotency key (in-flight or already responded)

### `GET /api/v1/payouts/`
Lists all payouts for the authenticated merchant, newest first.

### `GET /api/v1/payouts/{id}/`
Returns a single payout by ID.

### `GET /api/v1/ledger/`
Returns the last 50 ledger entries (credits and debits) for the merchant.

---

## Running Tests

```bash
cd backend
# Requires a running PostgreSQL database (the test runner creates its own test DB)

pytest payouts/tests/ -v

# Run concurrency test with verbose output
pytest payouts/tests/test_payouts.py::test_concurrent_payouts_one_succeeds -v -s

# Run all tests
pytest -v
```

### Test descriptions

| Test | What it proves |
|---|---|
| `test_concurrent_payouts_one_succeeds` | 10 threads, 1 success: `SELECT FOR UPDATE` prevents overdraft |
| `test_idempotency_same_key_no_duplicate` | Same key twice → 1 payout row, identical responses |
| `test_idempotency_key_scoped_per_merchant` | Same UUID, different merchants → independent payouts |
| `test_state_machine_blocks_failed_to_completed` | `failed → completed` raises `InvalidStateTransitionError` |
| `test_failed_payout_refunds_funds_atomically` | Failure restores balance atomically |
| `test_insufficient_funds_rejected` | Overdraft attempt returns 402, no payout created |

---

## Architecture Notes

### Why a ledger model instead of a balance column?

Every balance change is a `LedgerEntry` row (CREDIT or DEBIT). Balance is computed via a single SQL aggregate:

```sql
SELECT COALESCE(SUM(CASE WHEN type='CREDIT' THEN amount ELSE -amount END), 0)
FROM ledger_entries WHERE merchant_id = $1
```

This makes the ledger the single source of truth. Reversals (failed payout refunds) are new CREDIT rows, not UPDATEs — so nothing can be silently lost.

### Why `SELECT FOR UPDATE`?

Balance check + debit must be atomic. `SELECT FOR UPDATE` acquires an exclusive row-level lock on the merchant, serializing all concurrent payout requests for that merchant at the database level. Python-level locks don't protect across multiple OS processes (Gunicorn workers).

### Payout lifecycle

```
POST /api/v1/payouts/
  → validate idempotency key
  → SELECT FOR UPDATE (merchant)
  → check balance
  → INSERT payout (pending) + DEBIT ledger entry
  → COMMIT
  → celery task enqueued

Celery task (process_payout):
  → payout → processing
  → simulate bank: 70% success / 20% fail / 10% hang

Celery Beat (every 30s — reap_stuck_payouts):
  → find payouts in processing > 30s
  → retry up to 3 times (exponential backoff: 5s, 25s, 125s)
  → after 3 failures → FAILED + compensating CREDIT refund
```

---

## Project Structure

```
founderoffice-code/
├── backend/
│   ├── config/            Django settings, URLs, Celery config
│   ├── merchants/         Merchant model, seed command, profile API
│   ├── ledger/            LedgerEntry model, SQL balance query
│   ├── payouts/
│   │   ├── models.py      Payout + IdempotencyKey models
│   │   ├── state_machine.py  Legal transition whitelist
│   │   ├── services.py    SELECT FOR UPDATE locking + atomic operations
│   │   ├── tasks.py       Celery tasks (process_payout, reap_stuck_payouts)
│   │   ├── views.py       REST API views with full idempotency flow
│   │   └── tests/         Concurrency, idempotency, state machine tests
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx        Root component with auth + data fetching
│   │   ├── api.js         Axios client with token auth
│   │   └── components/
│   │       ├── LoginForm.jsx
│   │       ├── BalanceCard.jsx   Available + held balance
│   │       ├── PayoutForm.jsx    Payout request with auto-generated idempotency key
│   │       └── PayoutHistory.jsx Live-polling status updates
│   └── Dockerfile
├── docker-compose.yml
├── EXPLAINER.md           Technical deep-dive (ledger, lock, idempotency, state machine, AI audit)
└── README.md
```
