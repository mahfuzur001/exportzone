from django.urls import path

from . import views

app_name = "store"

urlpatterns = [
    path("", views.home, name="home"),
    path("shop/", views.shop, name="shop"),
    path("product/<slug:slug>/", views.product_detail, name="product_detail"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
]
