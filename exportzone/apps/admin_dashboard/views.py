from __future__ import annotations

from datetime import date
from decimal import Decimal
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.orders.models import Order, OrderItem, OrderStatusHistory
from apps.store.models import Category, Product, ProductImage, ProductVariant

from .forms import CategoryForm, OrderStatusForm, ProductForm, ProductImageForm, ProductVariantForm
from .services import change_order_status

LOW_STOCK_THRESHOLD = getattr(settings, "LOW_STOCK_THRESHOLD", 5)


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        if not request.user.is_staff:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped


def _order_queryset():
    item_qs = OrderItem.objects.select_related("product_variant")
    return Order.objects.select_related("user").prefetch_related(
        Prefetch("items", queryset=item_qs),
        "status_history__changed_by",
    )


@admin_required
def dashboard(request):
    non_cancelled = ~Q(status=Order.Status.CANCELLED)
    stats = {
        "total_orders": Order.objects.count(),
        "pending_orders": Order.objects.filter(status=Order.Status.PENDING).count(),
        "processing_orders": Order.objects.filter(status=Order.Status.PROCESSING).count(),
        "shipped_orders": Order.objects.filter(status=Order.Status.SHIPPED).count(),
        "delivered_orders": Order.objects.filter(status=Order.Status.DELIVERED).count(),
        "cancelled_orders": Order.objects.filter(status=Order.Status.CANCELLED).count(),
        "total_products": Product.objects.count(),
        "total_stock_units": ProductVariant.objects.aggregate(total=Sum("stock"))["total"] or 0,
        "out_of_stock_variants": ProductVariant.objects.filter(stock=0).count(),
        "low_stock_products": ProductVariant.objects.filter(stock__lte=LOW_STOCK_THRESHOLD).count(),
        "total_customers": get_user_model().objects.filter(is_staff=False).count(),
        "total_revenue": Order.objects.filter(non_cancelled).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00"),
    }
    today = timezone.localdate()
    today_qs = Order.objects.filter(created_at__date=today)
    stats["today_orders"] = today_qs.count()
    stats["today_revenue"] = today_qs.filter(non_cancelled).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")

    month_starts = []
    for offset in range(6):
        year = today.year + (today.month - 1 - offset) // 12
        month = (today.month - 1 - offset) % 12 + 1
        month_starts.append(date(year, month, 1))
    monthly_entries = []
    for index, start in enumerate(month_starts):
        if index + 1 < len(month_starts):
            end = month_starts[index + 1]
        elif start.month == 12:
            end = date(start.year + 1, 1, 1)
        else:
            end = date(start.year, start.month + 1, 1)
        revenue = (
            Order.objects.filter(created_at__date__gte=start, created_at__date__lt=end)
            .filter(non_cancelled)
            .aggregate(total=Sum("total_amount"))["total"]
            or Decimal("0.00")
        )
        monthly_entries.append({"label": start.strftime("%b %Y"), "revenue": revenue})
    peak = max((entry["revenue"] for entry in monthly_entries), default=Decimal("0.00"))
    for entry in monthly_entries:
        entry["pct"] = int(entry["revenue"] / peak * 100) if peak > 0 else 0

    recent_orders = _order_queryset()[:8]
    return render(
        request,
        "admin_dashboard/dashboard.html",
        {"stats": stats, "recent_orders": recent_orders, "monthly_sales": monthly_entries},
    )


@admin_required
def order_list(request):
    orders = _order_queryset()
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    ordering = request.GET.get("ordering", "-created_at")
    if query:
        orders = orders.filter(Q(order_number__icontains=query) | Q(user__email__icontains=query) | Q(user__phone__icontains=query) | Q(user__full_name__icontains=query))
    if status in dict(Order.Status.choices):
        orders = orders.filter(status=status)
    if date_from:
        orders = orders.filter(created_at__date__gte=date_from)
    if date_to:
        orders = orders.filter(created_at__date__lte=date_to)
    if ordering not in {"created_at", "-created_at", "total_amount", "-total_amount"}:
        ordering = "-created_at"
    page_obj = Paginator(orders.order_by(ordering), 20).get_page(request.GET.get("page"))
    return render(
        request,
        "admin_dashboard/orders.html",
        {
            "orders": page_obj.object_list,
            "page_obj": page_obj,
            "statuses": Order.Status.choices,
            "query": query,
            "selected_status": status,
            "ordering": ordering,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def order_detail(request, order_number):
    order = get_object_or_404(_order_queryset(), order_number=order_number)
    form = OrderStatusForm(request.POST or None, order=order)
    if request.method == "POST" and form.is_valid() and form.cleaned_data["status"] != order.status:
        try:
            order = change_order_status(order_number=order.order_number, status=form.cleaned_data["status"], changed_by=request.user, note=form.cleaned_data["note"])
        except Exception as error:
            form.add_error("status", str(error))
        else:
            messages.success(request, "Order status updated.")
            return redirect("admin_dashboard:order_detail", order_number=order.order_number)
    return render(request, "admin_dashboard/order_detail.html", {"order": order, "form": form, "status_history": order.status_history.all()})


@admin_required
def product_list(request):
    # Count and Sum share one join, so the unit total is not multiplied by the variant count.
    products = (
        Product.objects.select_related("category")
        .annotate(variant_count=Count("variants"), total_stock=Sum("variants__stock"))
        .order_by("-created_at")
    )
    query = request.GET.get("q", "").strip()
    if query:
        products = products.filter(Q(name__icontains=query) | Q(slug__icontains=query))
    page_obj = Paginator(products, 20).get_page(request.GET.get("page"))
    return render(request, "admin_dashboard/products.html", {"products": page_obj.object_list, "page_obj": page_obj, "query": query})


def _product_formsets(data=None, files=None, instance=None):
    from django.forms import inlineformset_factory

    VariantFormSet = inlineformset_factory(Product, ProductVariant, form=ProductVariantForm, extra=1, can_delete=True)
    ImageFormSet = inlineformset_factory(Product, ProductImage, form=ProductImageForm, extra=1, can_delete=True)
    return VariantFormSet(data, files, instance=instance, prefix="variants"), ImageFormSet(data, files, instance=instance, prefix="images")


@admin_required
def product_edit(request, product_id=None):
    product = get_object_or_404(Product, pk=product_id) if product_id else Product()
    form = ProductForm(request.POST or None, instance=product)
    variant_forms, image_forms = _product_formsets(request.POST or None, request.FILES or None, product)
    if request.method == "POST" and form.is_valid() and variant_forms.is_valid() and image_forms.is_valid():
        product = form.save()
        variant_forms.instance = product
        image_forms.instance = product
        variant_forms.save()
        image_forms.save()
        messages.success(request, "Product saved successfully.")
        return redirect("admin_dashboard:product_edit", product_id=product.pk)
    return render(request, "admin_dashboard/product_form.html", {"form": form, "variant_forms": variant_forms, "image_forms": image_forms, "product": product})


@admin_required
@require_POST
def product_delete(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    product.is_active = False
    product.save(update_fields=["is_active", "updated_at"])
    messages.info(request, "Product deactivated. Historical catalog records are preserved.")
    return redirect("admin_dashboard:products")


@admin_required
def category_list(request):
    categories = Category.objects.annotate(product_count=Count("products")).order_by("name")
    return render(request, "admin_dashboard/categories.html", {"categories": categories})


@admin_required
def category_edit(request, category_id=None):
    category = get_object_or_404(Category, pk=category_id) if category_id else Category()
    form = CategoryForm(request.POST or None, request.FILES or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category saved successfully.")
        return redirect("admin_dashboard:categories")
    return render(request, "admin_dashboard/category_form.html", {"form": form, "category": category})


@admin_required
@require_POST
def category_delete(request, category_id):
    category = get_object_or_404(Category.objects.annotate(product_count=Count("products")), pk=category_id)
    if category.product_count:
        messages.error(request, "Cannot delete a category that still has products.")
        return redirect("admin_dashboard:categories")
    category.delete()
    messages.info(request, "Category removed.")
    return redirect("admin_dashboard:categories")


@admin_required
def customer_list(request):
    User = get_user_model()
    customers = User.objects.filter(is_staff=False).annotate(order_count=Count("orders"), order_value=Sum("orders__total_amount")).order_by("-date_joined")
    query = request.GET.get("q", "").strip()
    if query:
        customers = customers.filter(Q(full_name__icontains=query) | Q(email__icontains=query) | Q(phone__icontains=query))
    page_obj = Paginator(customers, 20).get_page(request.GET.get("page"))
    return render(request, "admin_dashboard/customers.html", {"customers": page_obj.object_list, "page_obj": page_obj, "query": query})


@admin_required
def customer_detail(request, user_id):
    User = get_user_model()
    customer = get_object_or_404(
        User.objects.filter(is_staff=False).annotate(
            order_count=Count("orders"),
            order_value=Sum("orders__total_amount"),
        ),
        pk=user_id,
    )
    orders = customer.orders.all()[:10]
    return render(request, "admin_dashboard/customer_detail.html", {"customer": customer, "orders": orders})


@admin_required
@require_POST
def customer_toggle_active(request, user_id):
    User = get_user_model()
    customer = get_object_or_404(User.objects.filter(is_staff=False), pk=user_id)
    if customer.pk == request.user.pk:
        messages.error(request, "You cannot change your own account status here.")
        return redirect("admin_dashboard:customer_detail", user_id=customer.pk)
    customer.is_active = not customer.is_active
    customer.save(update_fields=["is_active", "updated_at"])
    messages.success(request, "Customer account status updated.")
    return redirect("admin_dashboard:customer_detail", user_id=customer.pk)


@admin_required
def low_stock(request):
    variants = ProductVariant.objects.select_related("product", "product__category").filter(stock__lte=LOW_STOCK_THRESHOLD).order_by("stock", "product__name")
    page_obj = Paginator(variants, 25).get_page(request.GET.get("page"))
    return render(request, "admin_dashboard/low_stock.html", {"variants": page_obj.object_list, "page_obj": page_obj, "threshold": LOW_STOCK_THRESHOLD})
