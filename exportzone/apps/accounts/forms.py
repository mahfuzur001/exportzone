from __future__ import annotations

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import (
    PasswordChangeForm as DjangoPasswordChangeForm,
)
from django.contrib.auth.forms import (
    PasswordResetForm,
    ReadOnlyPasswordHashField,
    SetPasswordForm,
)
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Address, bangladesh_phone_validator


class PremiumFormMixin:
    """Attach a single accessible visual system to Django form widgets."""

    def apply_premium_widgets(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check")
            else:
                field.widget.attrs.setdefault("class", "form-control")
                field.widget.attrs.setdefault("placeholder", field.label)
                field.widget.attrs.setdefault("autocomplete", "off")


class RegistrationForm(PremiumFormMixin, forms.Form):
    full_name = forms.CharField(max_length=150, label="Full name")
    email = forms.EmailField(label="Email address")
    phone = forms.CharField(max_length=11, label="Phone number")
    password1 = forms.CharField(
        label="Password", strip=False, widget=forms.PasswordInput(render_value=False)
    )
    password2 = forms.CharField(
        label="Confirm password", strip=False, widget=forms.PasswordInput(render_value=False)
    )
    agree_to_terms = forms.BooleanField(
        label="I agree to the Terms of Service and Privacy Policy.",
        error_messages={"required": "You must accept the terms to create an account."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_premium_widgets()
        self.fields["full_name"].widget.attrs["autocomplete"] = "name"
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["phone"].widget.attrs["autocomplete"] = "tel"
        self.fields["phone"].widget.attrs["inputmode"] = "numeric"
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"

    def clean_full_name(self):
        full_name = self.cleaned_data["full_name"].strip()
        if len(full_name) < 2:
            raise ValidationError("Enter your full name.")
        return full_name

    def clean_email(self):
        user_model = get_user_model()
        email = user_model.objects.normalize_email(self.cleaned_data["email"]).lower()
        if user_model.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_phone(self):
        user_model = get_user_model()
        phone = self.cleaned_data["phone"].strip()
        bangladesh_phone_validator(phone)
        if user_model.objects.filter(phone=phone).exists():
            raise ValidationError("This phone number is already registered.")
        return phone

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2:
            if password1 != password2:
                self.add_error("password2", "The passwords do not match.")
            else:
                user_model = get_user_model()
                user = user_model(
                    email=cleaned_data.get("email", ""),
                    phone=cleaned_data.get("phone", ""),
                    full_name=cleaned_data.get("full_name", ""),
                )
                validate_password(password1, user)
        return cleaned_data

    def save(self):
        """Create a ready-to-use account; sign-in is never gated by email."""
        return get_user_model().objects.create_user(
            email=self.cleaned_data["email"],
            phone=self.cleaned_data["phone"],
            full_name=self.cleaned_data["full_name"],
            password=self.cleaned_data["password1"],
        )


class LoginForm(PremiumFormMixin, forms.Form):
    identifier = forms.CharField(label="Email or phone")
    password = forms.CharField(
        label="Password", strip=False, widget=forms.PasswordInput(render_value=False)
    )
    remember_me = forms.BooleanField(label="Remember me", required=False)

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)
        self.apply_premium_widgets()
        self.fields["identifier"].widget.attrs["autocomplete"] = "username"
        self.fields["password"].widget.attrs["autocomplete"] = "current-password"

    def clean(self):
        cleaned_data = super().clean()
        identifier = cleaned_data.get("identifier", "").strip()
        password = cleaned_data.get("password")
        if not identifier or not password:
            return cleaned_data

        self.user_cache = authenticate(self.request, username=identifier, password=password)
        if self.user_cache is not None:
            return cleaned_data

        raise ValidationError("Invalid email/phone or password.")

    def get_user(self):
        return self.user_cache


class PasswordResetRequestForm(PremiumFormMixin, PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_premium_widgets()
        self.fields["email"].widget.attrs["autocomplete"] = "email"


class PremiumSetPasswordForm(PremiumFormMixin, SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_premium_widgets()
        for field in self.fields.values():
            field.widget.attrs["autocomplete"] = "new-password"


class AdminUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    class Meta:
        model = get_user_model()
        fields = ("email", "phone", "full_name", "is_active", "is_staff")

    def clean_password2(self):
        password2 = self.cleaned_data.get("password2")
        if self.cleaned_data.get("password1") != password2:
            raise ValidationError("The passwords do not match.")
        validate_password(password2, self.instance)
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            self.save_m2m()
        return user


class AdminUserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(label="Password")

    class Meta:
        model = get_user_model()
        fields = "__all__"

    def clean_password(self):
        return self.initial["password"]


class AddressForm(PremiumFormMixin, forms.ModelForm):
    class Meta:
        model = Address
        fields = ("full_name", "phone", "address", "area", "is_default")
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_premium_widgets()
        self.fields["full_name"].widget.attrs["autocomplete"] = "name"
        self.fields["phone"].widget.attrs["autocomplete"] = "tel"
        self.fields["phone"].widget.attrs["inputmode"] = "numeric"

    def clean_full_name(self):
        full_name = self.cleaned_data["full_name"].strip()
        if len(full_name) < 2:
            raise ValidationError("Enter a recipient name.")
        return full_name

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        bangladesh_phone_validator(phone)
        return phone

    def clean_address(self):
        address = self.cleaned_data["address"].strip()
        if not address:
            raise ValidationError("Enter a street address.")
        return address

    def clean_area(self):
        area = self.cleaned_data["area"].strip()
        if not area:
            raise ValidationError("Enter an area or district.")
        return area


class PasswordChangeForm(PremiumFormMixin, DjangoPasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_premium_widgets()
        for index, name in enumerate(self.fields):
            widget = self.fields[name].widget
            if not isinstance(widget, forms.CheckboxInput):
                widget.attrs["autocomplete"] = (
                    "current-password" if index == 0 else "new-password"
                )
