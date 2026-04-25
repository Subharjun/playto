"""
Payout API views.

POST /api/v1/payouts/
    Creates a payout. Requires 'Idempotency-Key' header (UUID).
    Idempotency flow:
        1. Parse and validate the UUID from the header.
        2. Try to fetch an existing IdempotencyKey row for (key, merchant).
        3. If found and not expired:
            a. Has response_body → return cached response immediately.
            b. No response_body → first request still in-flight → 409 Conflict.
        4. If not found: create the row (no response yet), run the payout logic.
        5. Cache the response on the IdempotencyKey row.

GET /api/v1/payouts/
    Lists all payouts for the authenticated merchant, newest first.

GET /api/v1/payouts/{id}/
    Returns a single payout. 404 if not found or belongs to another merchant.
"""

import uuid
import logging
from django.db import IntegrityError, transaction
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import Payout, IdempotencyKey
from .serializers import PayoutSerializer, PayoutCreateSerializer
from .services import create_payout_atomic, InsufficientFundsError
from ledger.serializers import LedgerEntrySerializer
from ledger.models import LedgerEntry

logger = logging.getLogger(__name__)


def _parse_idempotency_key(request) -> tuple[uuid.UUID | None, Response | None]:
    """Parse and validate the Idempotency-Key header. Returns (uuid, None) or (None, error_response)."""
    raw = request.headers.get("Idempotency-Key")
    if not raw:
        return None, Response(
            {"error": "Idempotency-Key header is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        return uuid.UUID(raw), None
    except ValueError:
        return None, Response(
            {"error": "Idempotency-Key must be a valid UUID (e.g. 550e8400-e29b-41d4-a716-446655440000)."},
            status=status.HTTP_400_BAD_REQUEST,
        )


class PayoutListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        POST /api/v1/payouts/

        Required header: Idempotency-Key: <UUID>
        Body: { "amount_paise": int, "bank_account_id": str }
        """
        merchant = request.user.merchant

        # 1. Validate idempotency key header
        idem_uuid, err = _parse_idempotency_key(request)
        if err:
            return err

        # 2. Check for existing idempotency key (scoped to this merchant)
        try:
            existing_key = IdempotencyKey.objects.get(key=idem_uuid, merchant=merchant)
        except IdempotencyKey.DoesNotExist:
            existing_key = None

        if existing_key:
            if existing_key.is_expired():
                # Expired key — treat as new request, delete old record
                existing_key.delete()
            elif existing_key.response_body is not None:
                # Cached response: return exactly what we returned the first time
                logger.info(
                    "Idempotency cache hit for key %s, merchant %s",
                    idem_uuid,
                    merchant.id,
                )
                return Response(
                    existing_key.response_body,
                    status=existing_key.response_status,
                )
            else:
                # First request still in-flight (no response cached yet)
                return Response(
                    {
                        "error": "A request with this Idempotency-Key is already in progress.",
                        "detail": "Retry after a few seconds if the first request has not returned.",
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        # 3. Create the idempotency key row (with no response yet)
        # Use get_or_create inside a try block to handle the race where two requests
        # with the same key arrive simultaneously. The UNIQUE constraint prevents
        # both from inserting — the loser will see the IntegrityError and should retry.
        try:
            with transaction.atomic():
                idem_key_obj, created = IdempotencyKey.objects.get_or_create(
                    key=idem_uuid,
                    merchant=merchant,
                    defaults={"response_status": None, "response_body": None},
                )
        except IntegrityError:
            return Response(
                {"error": "Concurrent request with the same Idempotency-Key detected."},
                status=status.HTTP_409_CONFLICT,
            )

        if not created:
            # Another concurrent request already inserted this key
            if idem_key_obj.response_body is not None:
                return Response(idem_key_obj.response_body, status=idem_key_obj.response_status)
            return Response(
                {"error": "A request with this Idempotency-Key is already in progress."},
                status=status.HTTP_409_CONFLICT,
            )

        # 4. Validate request body
        serializer = PayoutCreateSerializer(data=request.data)
        if not serializer.is_valid():
            # Cache the validation error response so the same bad key returns the same error
            error_response = serializer.errors
            idem_key_obj.response_status = status.HTTP_400_BAD_REQUEST
            idem_key_obj.response_body = error_response
            idem_key_obj.save(update_fields=["response_status", "response_body"])
            return Response(error_response, status=status.HTTP_400_BAD_REQUEST)

        amount_paise = serializer.validated_data["amount_paise"]
        bank_account_id = serializer.validated_data["bank_account_id"]

        # 5. Create payout (SELECT FOR UPDATE + balance check + DEBIT entry, all atomic)
        try:
            payout = create_payout_atomic(
                merchant=merchant,
                amount_paise=amount_paise,
                bank_account_id=bank_account_id,
                idempotency_key_obj=idem_key_obj,
            )
        except InsufficientFundsError as e:
            error_response = {"error": str(e)}
            idem_key_obj.response_status = status.HTTP_402_PAYMENT_REQUIRED
            idem_key_obj.response_body = error_response
            idem_key_obj.save(update_fields=["response_status", "response_body"])
            return Response(error_response, status=status.HTTP_402_PAYMENT_REQUIRED)
        except Exception as e:
            logger.exception("Unexpected error creating payout: %s", e)
            # Don't cache server errors — let the client retry with the same key
            idem_key_obj.delete()
            return Response(
                {"error": "Internal server error. Please retry."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 6. Cache the success response
        response_data = PayoutSerializer(payout).data
        # Convert UUID fields to strings for JSON serialization
        response_data = dict(response_data)
        response_data["id"] = str(response_data["id"])
        response_data["merchant"] = str(response_data["merchant"])

        idem_key_obj.response_status = status.HTTP_201_CREATED
        idem_key_obj.response_body = response_data
        idem_key_obj.save(update_fields=["response_status", "response_body"])

        return Response(response_data, status=status.HTTP_201_CREATED)

    def get(self, request):
        """GET /api/v1/payouts/ — list all payouts for the authenticated merchant."""
        merchant = request.user.merchant
        payouts = Payout.objects.filter(merchant=merchant).order_by("-created_at")
        serializer = PayoutSerializer(payouts, many=True)
        return Response(serializer.data)


class PayoutDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, payout_id):
        """GET /api/v1/payouts/{id}/ — retrieve a specific payout."""
        try:
            payout = Payout.objects.get(pk=payout_id, merchant=request.user.merchant)
        except (Payout.DoesNotExist, ValueError):
            return Response({"error": "Payout not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(PayoutSerializer(payout).data)


class LedgerView(APIView):
    """
    GET /api/v1/ledger/
    Returns the full ledger history for the authenticated merchant.
    Used by the dashboard to show recent credits and debits.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        merchant = request.user.merchant
        entries = LedgerEntry.objects.filter(merchant=merchant).order_by("-created_at")[:50]
        serializer = LedgerEntrySerializer(entries, many=True)
        return Response(serializer.data)
