from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .emailing import send_welcome_email
from .forms import (
    AddressForm,
    LoginForm,
    PasswordChangeForm,
    PasswordResetRequestForm,
    PremiumSetPasswordForm,
    RegistrationForm,
)
from .models import Address


def _safe_next_url(request) -> str | None:
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return None


def _post_login_redirect(user, next_url: str | None) -> str:
    """Honour an explicit ``?next=``, otherwise send staff to the console."""
    if next_url:
        return next_url
    if getattr(user, "is_staff", False):
        return reverse("admin_dashboard:dashboard")
    return settings.LOGIN_REDIRECT_URL


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:account")

    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        send_welcome_email(user)
        messages.success(
            request,
            f"Your account has been created successfully. A welcome email is on its way to {user.email}.",
        )
        return redirect("accounts:login")
    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:account")

    form = LoginForm(request, request.POST or None)
    next_url = _safe_next_url(request)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        if form.cleaned_data["remember_me"]:
            request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        else:
            request.session.set_expiry(0)
        messages.success(request, "Welcome back to EXPORT ZONE.")
        return redirect(_post_login_redirect(form.get_user(), next_url))
    return render(request, "accounts/login.html", {"form": form, "next": next_url or ""})


@require_POST
@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect(settings.LOGOUT_REDIRECT_URL)


@login_required
def account(request):
    from apps.orders.models import Order

    orders = Order.objects.filter(user=request.user)
    addresses = request.user.addresses.all()
    context = {
        "order_count": orders.count(),
        "recent_orders": list(orders.prefetch_related("items")[:5]),
        "address_count": addresses.count(),
        "default_address": addresses.filter(is_default=True).first()
        or addresses.first(),
    }
    return render(request, "accounts/account.html", context)


class BrandedPasswordResetView(PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.html"
    html_email_template_name = "registration/password_reset_email_html.html"
    subject_template_name = "registration/password_reset_subject.txt"
    form_class = PasswordResetRequestForm
    success_url = reverse_lazy("accounts:password_reset_done")

    def form_valid(self, form):
        messages.success(
            self.request,
            "If an eligible account uses that email, a password-reset link has been sent.",
        )
        return super().form_valid(form)


class BrandedPasswordResetDoneView(PasswordResetDoneView):
    template_name = "registration/password_reset_done.html"


class BrandedPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "registration/password_reset_confirm.html"
    form_class = PremiumSetPasswordForm
    success_url = reverse_lazy("accounts:password_reset_complete")


class BrandedPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "registration/password_reset_complete.html"


@login_required
def address_list(request):
    addresses = request.user.addresses.all()
    return render(
        request,
        "accounts/address_list.html",
        {"addresses": addresses},
    )


@login_required
def address_add(request):
    form = AddressForm(request.POST or None)
    if request.method == "GET":
        form.initial.update(
            {"full_name": request.user.full_name, "phone": request.user.phone}
        )
    if request.method == "POST" and form.is_valid():
        address = form.save(commit=False)
        address.user = request.user
        if not request.user.addresses.exists():
            address.is_default = True
        address.save()
        messages.success(request, "Address saved.")
        return redirect("accounts:address_list")
    return render(
        request,
        "accounts/address_form.html",
        {"form": form, "form_title": "Add address", "submit_label": "Save address"},
    )


@login_required
def address_edit(request, address_id):
    address = get_object_or_404(Address, pk=address_id, user=request.user)
    form = AddressForm(request.POST or None, instance=address)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Address updated.")
        return redirect("accounts:address_list")
    return render(
        request,
        "accounts/address_form.html",
        {"form": form, "form_title": "Edit address", "submit_label": "Update address"},
    )


@login_required
@require_POST
def address_delete(request, address_id):
    address = get_object_or_404(Address, pk=address_id, user=request.user)
    was_default = address.is_default
    address.delete()
    if was_default:
        next_address = request.user.addresses.first()
        if next_address is not None:
            next_address.is_default = True
            next_address.save(update_fields=["is_default", "updated_at"])
    messages.success(request, "Address removed.")
    return redirect("accounts:address_list")


@login_required
@require_POST
def address_set_default(request, address_id):
    address = get_object_or_404(Address, pk=address_id, user=request.user)
    with transaction.atomic():
        Address.objects.filter(user=request.user).update(is_default=False)
        address.is_default = True
        address.save(update_fields=["is_default", "updated_at"])
    messages.success(request, "Default address updated.")
    return redirect("accounts:address_list")


@login_required
def change_password(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Your password has been changed successfully.")
        return redirect("accounts:account")
    return render(request, "accounts/password_change.html", {"form": form})
