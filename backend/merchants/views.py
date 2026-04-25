from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import status
from django.db import transaction
from .models import Merchant
from .serializers import MerchantSerializer


class SignupView(APIView):
    """
    POST /api/v1/merchants/signup/
    
    Registers a new merchant account and returns an API token.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        company_name = request.data.get("company_name")
        bank_account_id = request.data.get("bank_account_id")

        if not all([email, password, company_name, bank_account_id]):
            return Response(
                {"error": "All fields are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(email=email).exists():
            return Response(
                {"error": "An account with this email already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                )
                Merchant.objects.create(
                    user=user,
                    name=company_name,
                    email=email,
                    bank_account_id=bank_account_id,
                )
                token, _ = Token.objects.get_or_create(user=user)
                return Response({"token": token.key}, status=status.HTTP_201_CREATED)
        except Exception:
            return Response(
                {"error": "Failed to create account. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LoginView(APIView):
    """
    POST /api/v1/merchants/login/
    
    Accepts email and password, returns the merchant's API token.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"error": "Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"error": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user = authenticate(username=user.username, password=password)
        if not user:
            return Response(
                {"error": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key})


class MerchantMeView(APIView):
    """
    GET /api/v1/merchants/me/

    Returns the authenticated merchant's profile, available balance, and held balance.
    Balance is computed from the ledger (a single SQL aggregate), never from a stored column.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        merchant = request.user.merchant
        serializer = MerchantSerializer(merchant)
        return Response(serializer.data)
