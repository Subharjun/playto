from django.urls import path
from .views import PayoutListCreateView, PayoutDetailView, LedgerView

urlpatterns = [
    path("payouts/", PayoutListCreateView.as_view(), name="payout-list-create"),
    path("payouts/<uuid:payout_id>/", PayoutDetailView.as_view(), name="payout-detail"),
    path("ledger/", LedgerView.as_view(), name="ledger"),
]
