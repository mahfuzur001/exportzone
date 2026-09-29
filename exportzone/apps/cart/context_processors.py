from django.db.models import Case, IntegerField, Sum, Value, When

from apps.store.models import Category

from .models import Cart

# Spec navigation priority: show the main catalog categories first.
NAV_CATEGORY_PRIORITY = ("Jeans", "Shirts", "Polo T-Shirts", "T-Shirts")


def cart_summary(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"cart_item_count": 0}

    item_count = (
        Cart.objects.filter(user=user)
        .aggregate(total=Sum("items__quantity"))
        .get("total")
        or 0
    )
    return {"cart_item_count": item_count}


def footer_categories(request):
    """Expose active catalog categories to base layout templates."""
    priority_order = Case(
        *[
            When(name=name, then=Value(index))
            for index, name in enumerate(NAV_CATEGORY_PRIORITY)
        ],
        default=Value(len(NAV_CATEGORY_PRIORITY)),
        output_field=IntegerField(),
    )
    return {
        "footer_categories": Category.objects.filter(is_active=True).order_by(
            priority_order,
            "name",
        )
    }
