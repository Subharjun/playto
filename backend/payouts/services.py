"""
Payout service layer — business logic lives here, not in views or tasks.

The critical section is create_payout_atomic(). It:
1. Acquires a SELECT FOR UPDATE row lock on the Merchant row.
2. Computes available balance via SQL aggregate inside that transaction.
3. Checks sufficiency (balance >= amount).
4. Creates the Payout record.
5. Creates a DEBIT LedgerEntry for the held amount.
6. All within a single atomic transaction — so no other concurrent request
   can interleave between the check and the deduct.

WHY SELECT FOR UPDATE on the Merchant row?
    We need to serialize all payout requests for the same merchant.
    Locking the LedgerEntry table directly is too coarse (locks all merchants).
    The Merchant row is a natural serialization point — one row per merchant,
    one lock per merchant, other merchants are unaffected.

    Python-level locks (threading.Lock) are wrong — they don't protect across
    Gunicorn workers or separate processes. Only database locks work here.
"""

import uuid
import logging
from django.db import transaction
from django.db.models import Sum, Case, When, Value, BigIntegerField
from django.db.models.functions import Coalesce
from django.utils import timezone

from merchants.models import Merchant
from ledger.models import LedgerEntry, EntryType
from .models import Payout, PayoutStatus, IdempotencyKey
from .state_machine import assert_legal_transition, InvalidStateTransitionError
from . import tasks as payout_tasks

logger = logging.getLogger(__name__)


class InsufficientFundsError(Exception):
    pass


class PayoutNotFoundError(Exception):
    pass


def create_payout_atomic(
    merchant: Merchant,
    amount_paise: int,
    bank_account_id: str,
    idempotency_key_obj: IdempotencyKey,
) -> Payout:
    """
    Creates a payout and holds the funds atomically.

    This is the hot path. The SELECT FOR UPDATE on merchant ensures exactly one
    concurrent payout creation proceeds at a time for a given merchant.
    The balance check and DEBIT write happen inside the same transaction,
    so there is no window for a race condition.

    On success: returns the Payout object (status=pending).
    On failure: raises InsufficientFundsError (no DB changes made).
    """
    with transaction.atomic():
        # Lock the merchant row for the duration of this transaction.
        # Any other request trying to SELECT FOR UPDATE on this merchant will block
        # here until we commit, guaranteeing serial execution.
        merchant_locked = Merchant.objects.select_for_update().get(pk=merchant.pk)

        # Compute available balance entirely in SQL. No Python summation.
        # This reflects the post-lock state — all prior committed debits are visible.
        balance_result = LedgerEntry.objects.filter(merchant=merchant_locked).aggregate(
            available=Coalesce(
                Sum(
                    Case(
                        When(entry_type=EntryType.CREDIT, then="amount_paise"),
                        default=Value(0),
                        output_field=BigIntegerField(),
                    )
                )
                - Sum(
                    Case(
                        When(entry_type=EntryType.DEBIT, then="amount_paise"),
                        default=Value(0),
                        output_field=BigIntegerField(),
                    )
                ),
                Value(0),
                output_field=BigIntegerField(),
            )
        )
        available = balance_result["available"]

        if available < amount_paise:
            raise InsufficientFundsError(
                f"Insufficient funds. Available: {available}p, Requested: {amount_paise}p"
            )

        # Create the payout record
        payout = Payout.objects.create(
            merchant=merchant_locked,
            amount_paise=amount_paise,
            bank_account_id=bank_account_id,
            status=PayoutStatus.PENDING,
            idempotency_key=idempotency_key_obj,
        )

        # Atomically debit the ledger — funds are now "held"
        LedgerEntry.objects.create(
            merchant=merchant_locked,
            amount_paise=amount_paise,
            entry_type=EntryType.DEBIT,
            reference_id=payout.id,
            description=f"Hold for payout {payout.id}",
        )

    # Transaction committed. Now enqueue the background task.
    # This is OUTSIDE the transaction — if task enqueueing fails, the payout
    # is still in pending state and the reaper task will pick it up.
    payout_tasks.process_payout.delay(str(payout.id))
    logger.info("Enqueued process_payout task for payout %s", payout.id)

    return payout


def mark_payout_processing(payout_id: str) -> Payout:
    """
    Transitions payout from pending → processing.
    Called by the Celery task at the start of processing.
    Uses SELECT FOR UPDATE to prevent concurrent task execution on the same payout.
    """
    with transaction.atomic():
        try:
            payout = Payout.objects.select_for_update().get(pk=payout_id)
        except Payout.DoesNotExist:
            raise PayoutNotFoundError(f"Payout {payout_id} not found")

        assert_legal_transition(payout.status, PayoutStatus.PROCESSING)
        payout.status = PayoutStatus.PROCESSING
        payout.processing_started_at = timezone.now()
        payout.attempt_count += 1
        payout.save(update_fields=["status", "processing_started_at", "attempt_count", "updated_at"])

    return payout


def mark_payout_completed(payout_id: str) -> Payout:
    """
    Transitions payout from processing → completed.
    Funds were already debited on creation — no ledger entry needed on success.
    The DEBIT entry is the permanent record of the outgoing payment.
    """
    with transaction.atomic():
        try:
            payout = Payout.objects.select_for_update().get(pk=payout_id)
        except Payout.DoesNotExist:
            raise PayoutNotFoundError(f"Payout {payout_id} not found")

        assert_legal_transition(payout.status, PayoutStatus.COMPLETED)
        payout.status = PayoutStatus.COMPLETED
        payout.save(update_fields=["status", "updated_at"])
        logger.info("Payout %s completed successfully", payout_id)

    return payout


def mark_payout_failed(payout_id: str, reason: str) -> Payout:
    """
    Transitions payout from processing → failed AND refunds the held amount.

    CRITICAL: The refund (compensating CREDIT entry) is written atomically
    with the state transition in the same transaction. If either fails, both
    roll back. This ensures funds can never vanish — either the payout completes
    and the DEBIT stands, or it fails and a CREDIT reversal is created.

    This is why we use a ledger model instead of a balance column: reversal is
    just another row, not an UPDATE that could conflict with concurrent reads.
    """
    with transaction.atomic():
        try:
            payout = Payout.objects.select_for_update().get(pk=payout_id)
        except Payout.DoesNotExist:
            raise PayoutNotFoundError(f"Payout {payout_id} not found")

        assert_legal_transition(payout.status, PayoutStatus.FAILED)
        payout.status = PayoutStatus.FAILED
        payout.failure_reason = reason
        payout.save(update_fields=["status", "failure_reason", "updated_at"])

        # Compensating credit — atomically restores the merchant's balance
        LedgerEntry.objects.create(
            merchant=payout.merchant,
            amount_paise=payout.amount_paise,
            entry_type=EntryType.CREDIT,
            reference_id=payout.id,
            description=f"Refund for failed payout {payout.id}: {reason}",
        )
        logger.info("Payout %s failed. Funds refunded to merchant %s", payout_id, payout.merchant_id)

    return payout
