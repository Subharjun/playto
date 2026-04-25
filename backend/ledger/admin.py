from django.contrib import admin
from .models import LedgerEntry


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("merchant", "entry_type", "amount_paise", "reference_id", "created_at")
    list_filter = ("entry_type", "merchant")
    search_fields = ("merchant__name", "description")
    readonly_fields = ("id", "created_at")
    ordering = ("-created_at",)
