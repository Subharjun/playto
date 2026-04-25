"""
Seed management command.

Creates 3 test merchants with credit history (simulated customer payments).
Also creates a Django auth user + DRF token for each merchant so the frontend
can authenticate.

Usage:
    python manage.py seed
    python manage.py seed --reset   # drops existing seed data first
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework.authtoken.models import Token

from merchants.models import Merchant
from ledger.models import LedgerEntry, EntryType


SEED_MERCHANTS = [
    {
        "username": "acme_exports",
        "password": "testpass123",
        "name": "Acme Exports Pvt Ltd",
        "email": "acme@example.com",
        "bank_account_id": "ICICI_9876543210",
        "credits": [
            {"amount_paise": 5_000_00, "description": "Payment from GlobalCorp Inc (Invoice #1001)"},
            {"amount_paise": 3_500_00, "description": "Payment from TechVentures LLC (Invoice #1002)"},
            {"amount_paise": 2_000_00, "description": "Payment from Nordic Solutions AB (Invoice #1003)"},
        ],
    },
    {
        "username": "vikram_freelance",
        "password": "testpass123",
        "name": "Vikram Nair (Freelancer)",
        "email": "vikram@example.com",
        "bank_account_id": "HDFC_1122334455",
        "credits": [
            {"amount_paise": 1_200_00, "description": "Design project payment from StartupXYZ"},
            {"amount_paise": 800_00, "description": "Logo design - ClientABC"},
            {"amount_paise": 1_500_00, "description": "Brand identity project - USClient"},
        ],
    },
    {
        "username": "brightwave_agency",
        "password": "testpass123",
        "name": "BrightWave Digital Agency",
        "email": "brightwave@example.com",
        "bank_account_id": "AXIS_5566778899",
        "credits": [
            {"amount_paise": 10_000_00, "description": "Monthly retainer - EuropeCo (Apr 2025)"},
            {"amount_paise": 7_500_00, "description": "Campaign management - USBrand Q1"},
            {"amount_paise": 3_200_00, "description": "SEO project - AusClient"},
            {"amount_paise": 2_100_00, "description": "Content creation bundle - SingaporeCo"},
        ],
    },
]


class Command(BaseCommand):
    help = "Seed the database with test merchants and credit history"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing seed data before re-seeding",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write("Resetting existing seed data...")
            usernames = [m["username"] for m in SEED_MERCHANTS]
            User.objects.filter(username__in=usernames).delete()
            self.stdout.write(self.style.WARNING("Deleted existing merchants."))

        with transaction.atomic():
            for merchant_data in SEED_MERCHANTS:
                user, created = User.objects.get_or_create(
                    username=merchant_data["username"],
                    defaults={"email": merchant_data["email"]},
                )
                if created:
                    user.set_password(merchant_data["password"])
                    user.save()

                merchant, m_created = Merchant.objects.get_or_create(
                    email=merchant_data["email"],
                    defaults={
                        "user": user,
                        "name": merchant_data["name"],
                        "bank_account_id": merchant_data["bank_account_id"],
                    },
                )

                token, _ = Token.objects.get_or_create(user=user)

                if m_created:
                    for credit in merchant_data["credits"]:
                        LedgerEntry.objects.create(
                            merchant=merchant,
                            amount_paise=credit["amount_paise"],
                            entry_type=EntryType.CREDIT,
                            description=credit["description"],
                        )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Created merchant: {merchant.name} | Token: {token.key}"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"→ Merchant already exists: {merchant.name} | Token: {token.key}"
                        )
                    )

        self.stdout.write(self.style.SUCCESS("\nSeeding complete!"))
        self.stdout.write(
            "\nUse these tokens in the Authorization header: 'Token <token_value>'"
        )
