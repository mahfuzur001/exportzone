from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("forgot-password/", views.BrandedPasswordResetView.as_view(), name="password_reset"),
    path("forgot-password/done/", views.BrandedPasswordResetDoneView.as_view(), name="password_reset_done"),
    path("reset-password/<uidb64>/<token>/", views.BrandedPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset-password/complete/", views.BrandedPasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("account/", views.account, name="account"),
    path("account/addresses/", views.address_list, name="address_list"),
    path("account/addresses/add/", views.address_add, name="address_add"),
    path("account/addresses/<int:address_id>/edit/", views.address_edit, name="address_edit"),
    path("account/addresses/<int:address_id>/delete/", views.address_delete, name="address_delete"),
    path("account/addresses/<int:address_id>/default/", views.address_set_default, name="address_set_default"),
    path("account/password/", views.change_password, name="change_password"),
]
