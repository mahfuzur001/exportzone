from django.urls import path

from . import views

app_name = "admin_dashboard"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("orders/", views.order_list, name="orders"),
    path("orders/<str:order_number>/", views.order_detail, name="order_detail"),
    path("products/", views.product_list, name="products"),
    path("products/add/", views.product_edit, name="product_add"),
    path("products/<int:product_id>/edit/", views.product_edit, name="product_edit"),
    path("products/<int:product_id>/delete/", views.product_delete, name="product_delete"),
    path("categories/", views.category_list, name="categories"),
    path("categories/add/", views.category_edit, name="category_add"),
    path("categories/<int:category_id>/edit/", views.category_edit, name="category_edit"),
    path("categories/<int:category_id>/delete/", views.category_delete, name="category_delete"),
    path("customers/", views.customer_list, name="customers"),
    path("customers/<int:user_id>/", views.customer_detail, name="customer_detail"),
    path("customers/<int:user_id>/toggle-active/", views.customer_toggle_active, name="customer_toggle_active"),
    path("low-stock/", views.low_stock, name="low_stock"),
]
