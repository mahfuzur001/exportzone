from django import forms

from apps.store.models import Category, Product, ProductImage, ProductVariant


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ("category", "name", "slug", "description", "base_price", "is_active", "featured")
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}

    def clean_base_price(self):
        price = self.cleaned_data["base_price"]
        if price < 0:
            raise forms.ValidationError("Price cannot be negative.")
        return price


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ("name", "slug", "description", "image", "is_active")
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ("size", "color", "stock", "sku")

    def clean_stock(self):
        stock = self.cleaned_data["stock"]
        if stock < 0:
            raise forms.ValidationError("Stock cannot be negative.")
        return stock


ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ("image", "alt_text", "is_primary")

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image or not getattr(image, "content_type", None):
            return image
        if image.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise forms.ValidationError("Upload a JPEG, PNG, WebP, or GIF image.")
        if image.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Image must be 5 MB or smaller.")
        return image


class OrderStatusForm(forms.Form):
    status = forms.ChoiceField(choices=())
    note = forms.CharField(required=False, max_length=255, widget=forms.TextInput())

    def __init__(self, *args, order, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [(order.status, order.get_status_display())]
        choices.extend((value, label) for value, label in order.Status.choices if order.can_transition_to(value))
        self.fields["status"].choices = choices
