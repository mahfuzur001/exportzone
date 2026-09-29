from django import forms

from apps.accounts.models import bangladesh_phone_validator
from apps.store.forms import CouponForm

from .models import Order


class CheckoutForm(CouponForm, forms.Form):
    full_name = forms.CharField(max_length=150, strip=True)
    phone = forms.CharField(max_length=11, validators=[bangladesh_phone_validator])
    address = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), max_length=500, strip=True)
    area = forms.CharField(max_length=120, strip=True)
    delivery_note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), max_length=500, strip=True)
    payment_method = forms.ChoiceField(choices=[(Order.PaymentMethod.COD, "Cash on Delivery")], initial=Order.PaymentMethod.COD)
    delivery_option = forms.ChoiceField(choices=[("HOME_DELIVERY", "Home Delivery")], initial="HOME_DELIVERY")
    # Optional: an empty box simply means "no discount", so a blank submit is valid
    # and the order is placed at full price. The code itself is validated again inside
    # the order-creation transaction, which is what actually decides whether it counts.
    coupon_code = forms.CharField(
        max_length=40,
        required=False,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Discount code",
                "autocomplete": "off",
                "spellcheck": "false",
                "class": "w-full bg-ink/70 border border-white/20 px-3 py-2.5 text-sm uppercase tracking-[0.15em] text-cream placeholder:text-cream/35 focus:border-gold focus:outline-none",
            }
        ),
    )

    def clean_coupon_code(self):
        # Normalised here so the preview and the order creation compare the same
        # string; create_order_from_cart applies the same uppercase rule.
        return (self.cleaned_data.get("coupon_code") or "").strip().upper()

    def clean_payment_method(self):
        payment_method = self.cleaned_data["payment_method"]
        if payment_method != Order.PaymentMethod.COD:
            raise forms.ValidationError("Only Cash on Delivery is currently available.")
        return payment_method

    def clean(self):
        cleaned_data = super().clean()
        for field in ("full_name", "address", "area"):
            if field in cleaned_data and not cleaned_data[field]:
                self.add_error(field, "This field is required.")
        return cleaned_data
