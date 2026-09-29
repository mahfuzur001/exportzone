from __future__ import annotations

from django import forms

from apps.accounts.models import bangladesh_phone_validator

from .models import ContactMessage


class ContactForm(forms.ModelForm):
    """Validated public contact form with an optional Bangladesh phone number."""

    class Meta:
        model = ContactMessage
        fields = ("name", "email", "phone", "message")
        widgets = {
            "message": forms.Textarea(attrs={"rows": 5}),
            "name": forms.TextInput(attrs={"autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "phone": forms.TextInput(
                attrs={"autocomplete": "tel", "inputmode": "numeric"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        input_classes = (
            "w-full bg-ink/50 border border-white/20 rounded-sm text-cream "
            "px-4 py-3 focus:border-gold focus:ring-1 focus:ring-gold "
            "outline-none transition-colors placeholder:text-cream/35"
        )
        for name, field in self.fields.items():
            if name == "phone":
                field.widget.attrs["placeholder"] = "01XXXXXXXXX (optional)"
            field.widget.attrs.setdefault("class", input_classes)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if len(name) < 2:
            raise forms.ValidationError("Enter your name.")
        return name

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()
        if phone:
            bangladesh_phone_validator(phone)
        return phone

    def clean_message(self):
        message = self.cleaned_data["message"].strip()
        if len(message) < 5:
            raise forms.ValidationError("Tell us a little more about your message.")
        return message


class ReviewForm(forms.Form):
    """The public review form.

    ``order_item`` is a choice field rather than a free id, so the browser can only
    ever submit one of the order lines the service already proved this customer owns;
    the service re-checks it anyway, because a POST can carry any value.
    """

    order_item = forms.ModelChoiceField(queryset=None, widget=forms.Select)
    rating = forms.TypedChoiceField(
        choices=[(value, f"{value} star{'s' if value != 1 else ''}") for value in range(1, 6)],
        coerce=int,
    )
    title = forms.CharField(max_length=120, required=False)
    comment = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "What did you like or dislike? How does the fit run?"}),
    )

    def __init__(self, *args, purchasable_items=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["order_item"].queryset = purchasable_items
        if not purchasable_items:
            # Nothing is reviewable, so drop the select rather than render an empty one.
            del self.fields["order_item"]
        self.fields["rating"].widget.attrs["class"] = "sr-only"
        for name, field in self.fields.items():
            if name == "rating":
                continue
            field.widget.attrs.setdefault(
                "class",
                "w-full border border-white/20 bg-ink/60 px-4 py-3 text-sm text-cream "
                "focus:border-gold focus:outline-none",
            )

    def clean_rating(self):
        rating = self.cleaned_data.get("rating")
        if not rating or not 1 <= rating <= 5:
            raise forms.ValidationError("Choose a rating between 1 and 5 stars.")
        return rating

    def clean_comment(self):
        comment = self.cleaned_data.get("comment", "").strip()
        # A rating on its own is allowed, but a lone space is not a review.
        if not comment and not self.cleaned_data.get("title"):
            raise forms.ValidationError("Add a short comment so your review is useful to others.")
        return comment

    def clean_title(self):
        return self.cleaned_data.get("title", "").strip()


class CouponForm(forms.Form):
    """The discount code field on the checkout page."""

    coupon_code = forms.CharField(
        max_length=40,
        required=False,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Discount code",
                "autocomplete": "off",
                "class": (
                    "w-full border border-white/20 bg-ink/60 px-4 py-3 text-sm uppercase "
                    "tracking-[0.15em] text-cream placeholder:text-cream/35 "
                    "focus:border-gold focus:outline-none"
                ),
            }
        ),
    )
