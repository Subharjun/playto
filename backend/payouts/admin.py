from django.contrib import admin
from .models import Payout, IdempotencyKey


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("id", "merchant", "amount_paise", "status", "attempt_count", "created_at", "updated_at")
    list_filter = ("status", "merchant")
    search_fields = ("id", "merchant__name", "bank_account_id")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ("key", "merchant", "response_status", "created_at")
    list_filter = ("response_status",)
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
