from rest_framework import serializers
from .models import Merchant
from ledger.queries import get_merchant_balance


class MerchantSerializer(serializers.ModelSerializer):
    available_balance_paise = serializers.SerializerMethodField()
    held_balance_paise = serializers.SerializerMethodField()

    class Meta:
        model = Merchant
        fields = [
            "id",
            "name",
            "email",
            "bank_account_id",
            "available_balance_paise",
            "held_balance_paise",
            "created_at",
        ]

    def get_available_balance_paise(self, obj):
        return get_merchant_balance(obj)["available"]

    def get_held_balance_paise(self, obj):
        return get_merchant_balance(obj)["held"]
