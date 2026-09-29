from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/apply-coupon/", views.apply_coupon, name="apply_coupon"),
    path("order-success/<str:order_number>/", views.confirmation, name="confirmation"),
    path("account/orders/", views.order_list, name="list"),
    path("account/orders/<str:order_number>/", views.order_detail, name="detail"),
    path("account/orders/<str:order_number>/cancel/", views.cancel_order, name="cancel"),
]
