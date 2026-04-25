from rest_framework import serializers
from .models import LedgerEntry


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "amount_paise",
            "entry_type",
            "reference_id",
            "description",
            "created_at",
        ]
