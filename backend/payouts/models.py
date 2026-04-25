import uuid
from django.db import models
from django.utils import timezone


class PayoutStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class Payout(models.Model):
    """
    Represents a single payout request from a merchant.

    Lifecycle (state machine):
        pending → processing → completed
                            ↘ failed

    When a payout is created (pending), a DEBIT ledger entry is written atomically
    in the same transaction, holding the funds. If the payout fails, a compensating
    CREDIT entry is written atomically with the FAILED state transition.

    amount_paise: always BigIntegerField, never Float or Decimal.
    attempt_count: tracks how many times the Celery task has tried to process this.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.PROTECT,
        related_name="payouts",
    )
    amount_paise = models.BigIntegerField(
        help_text="Amount in paise. Must be positive. Never stored as float."
    )
    bank_account_id = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=PayoutStatus.choices,
        default=PayoutStatus.PENDING,
        db_index=True,
    )
    attempt_count = models.IntegerField(default=0)
    failure_reason = models.TextField(blank=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.ForeignKey(
        "IdempotencyKey",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payouts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payouts"
        indexes = [
            models.Index(fields=["merchant", "status"]),
            models.Index(fields=["status", "processing_started_at"]),
        ]

    def __str__(self):
        return f"Payout {self.id} — {self.status} — {self.amount_paise}p"


class IdempotencyKey(models.Model):
    """
    Stores idempotency keys to prevent duplicate payout creation.

    Keys are scoped per merchant (UNIQUE on key + merchant_id).
    A key without a response_body means the first request is still in-flight.
    Keys expire after 24 hours (checked at lookup time).

    The response_status and response_body cache the exact HTTP response
    returned to the first caller — subsequent calls with the same key
    get this cached response verbatim.
    """

    key = models.UUIDField()
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.CASCADE,
        related_name="idempotency_keys",
    )
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "idempotency_keys"
        unique_together = [("key", "merchant")]
        indexes = [
            models.Index(fields=["created_at"]),  # for expiry cleanup
        ]

    def is_expired(self):
        from django.conf import settings
        from datetime import timedelta
        ttl = settings.IDEMPOTENCY_KEY_TTL_SECONDS
        return timezone.now() > self.created_at + timedelta(seconds=ttl)

    def __str__(self):
        return f"IdempKey {self.key} — merchant {self.merchant_id}"
