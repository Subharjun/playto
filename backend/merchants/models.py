import uuid
from django.db import models


class Merchant(models.Model):
    """
    A merchant on the Playto Pay platform.

    Each merchant has a bank_account_id representing where payouts are sent.
    Authentication is handled via Django's built-in User + DRF Token.
    The merchant record is linked 1:1 to a User.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="merchant",
    )
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    bank_account_id = models.CharField(
        max_length=100,
        help_text="Simulated bank account identifier for payout settlement.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "merchants"

    def __str__(self):
        return f"{self.name} ({self.email})"
