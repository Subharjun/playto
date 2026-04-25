from rest_framework import serializers
from ledger.serializers import LedgerEntrySerializer
from .models import Payout


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = [
            "id",
            "merchant",
            "amount_paise",
            "bank_account_id",
            "status",
            "attempt_count",
            "failure_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "merchant",
            "status",
            "attempt_count",
            "failure_reason",
            "created_at",
            "updated_at",
        ]


class PayoutCreateSerializer(serializers.Serializer):
    """
    Validates the POST /api/v1/payouts/ request body.
    We use a non-model serializer here so we can apply custom validations
    before touching the DB.
    """
    amount_paise = serializers.IntegerField(
        min_value=1,
        help_text="Amount to payout in paise. Must be a positive integer.",
    )
    bank_account_id = serializers.CharField(
        max_length=100,
        help_text="Destination bank account identifier.",
    )

    def validate_amount_paise(self, value):
        # Minimum payout: 1 rupee (100 paise)
        if value < 100:
            raise serializers.ValidationError(
                "Minimum payout amount is 100 paise (1 INR)."
            )
        return value
