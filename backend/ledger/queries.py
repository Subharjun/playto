"""
Ledger balance queries.

All balance calculations use a single database-level SQL aggregation.
We never fetch rows to Python and sum them there — that is both slower and
incorrect under concurrent writes (dirty reads, lost updates).

The canonical balance query:

    SELECT
        COALESCE(SUM(CASE WHEN entry_type = 'CREDIT' THEN amount_paise ELSE 0 END), 0)
      - COALESCE(SUM(CASE WHEN entry_type = 'DEBIT'  THEN amount_paise ELSE 0 END), 0)
    FROM ledger_entries
    WHERE merchant_id = %s

Django ORM equivalent: use conditional aggregation via Case/When.
"""

from django.db.models import Sum, Case, When, Value, BigIntegerField
from django.db.models.functions import Coalesce

from .models import LedgerEntry, EntryType


def get_merchant_balance(merchant) -> dict:
    """
    Returns a dict with:
        available  — net spendable balance in paise (all credits minus all debits)
        held       — funds currently held for pending/processing payouts

    The 'held' figure is computed by summing DEBIT entries whose linked payout
    is still pending or processing. This lets the frontend show a useful split
    without storing balance in a separate column (which would be an extra
    invariant to maintain and a potential source of drift).

    This function issues ONE query for the available balance and ONE for held.
    Both are pure SQL aggregates — no Python-level summation.
    """
    result = LedgerEntry.objects.filter(merchant=merchant).aggregate(
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

    # Held balance: sum of DEBIT entries still linked to active (pending/processing) payouts.
    # Import here to avoid circular import at module load time.
    from payouts.models import Payout, PayoutStatus

    active_payout_ids = Payout.objects.filter(
        merchant=merchant,
        status__in=[PayoutStatus.PENDING, PayoutStatus.PROCESSING],
    ).values_list("id", flat=True)

    held = LedgerEntry.objects.filter(
        merchant=merchant,
        entry_type=EntryType.DEBIT,
        reference_id__in=active_payout_ids,
    ).aggregate(
        total=Coalesce(Sum("amount_paise"), Value(0), output_field=BigIntegerField())
    )["total"]

    return {
        "available": result["available"],
        "held": held,
    }
