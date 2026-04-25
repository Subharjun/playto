from django.contrib import admin
from .models import Merchant


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "bank_account_id", "created_at")
    search_fields = ("name", "email")
    readonly_fields = ("id", "created_at")
