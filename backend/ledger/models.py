import uuid
from django.db import models


class EntryType(models.TextChoices):
    CREDIT = "CREDIT", "Credit"
    DEBIT = "DEBIT", "Debit"


class LedgerEntry(models.Model):
    """
    The immutable ledger — source of truth for all money movement.

    Every balance change is a row here. Credits come from customer payments.
    Debits are created atomically when a payout is requested (holding the funds).
    If a payout fails, a compensating CREDIT entry is written in the same transaction
    as the FAILED state transition, so funds are never lost.

    CRITICAL INVARIANT:
        available_balance = SUM(amount_paise WHERE type=CREDIT) - SUM(amount_paise WHERE type=DEBIT)

    This is computed with a single SQL aggregate (see ledger/queries.py).
    We never do Python arithmetic on fetched rows — that would be wrong under concurrency.

    Fields:
        merchant     — which merchant this entry belongs to
        amount_paise — always positive (BigIntegerField, never Float/Decimal)
        entry_type   — CREDIT or DEBIT
        reference_id — optional UUID linking a DEBIT to its payout.id
        description  — human-readable reason for the entry
    """

    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        db_index=True,
    )
    amount_paise = models.BigIntegerField(
        help_text="Amount in paise (integer). 1 INR = 100 paise. Never a float."
    )
    entry_type = models.CharField(max_length=6, choices=EntryType.choices)
    reference_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="Links a DEBIT entry to its corresponding Payout UUID.",
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_entries"
        indexes = [
            # Compound index: merchant+time is the most common query pattern
            models.Index(fields=["merchant", "created_at"]),
            # Index for looking up all entries for a specific payout
            models.Index(fields=["reference_id"]),
        ]

    def __str__(self):
        return f"{self.entry_type} {self.amount_paise}p — {self.merchant}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.amount_paise is not None and self.amount_paise <= 0:
            raise ValidationError("amount_paise must be a positive integer.")
