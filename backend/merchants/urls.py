from django.urls import path
from .views import MerchantMeView, LoginView, SignupView, SimulatePaymentView

urlpatterns = [
    path("merchants/signup/", SignupView.as_view(), name="merchant-signup"),
    path("merchants/login/", LoginView.as_view(), name="merchant-login"),
    path("merchants/me/", MerchantMeView.as_view(), name="merchant-me"),
    path("merchants/simulate-payment/", SimulatePaymentView.as_view(), name="simulate-payment"),
]
