from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import AdminUserChangeForm, AdminUserCreationForm
from .models import Address, CustomUser


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "area", "user", "is_default", "updated_at")
    list_filter = ("is_default",)
    search_fields = ("full_name", "phone", "area", "address", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    add_form = AdminUserCreationForm
    form = AdminUserChangeForm
    model = CustomUser
    list_display = ("email", "full_name", "phone", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "is_superuser", "date_joined")
    search_fields = ("email", "phone", "full_name")
    ordering = ("email",)
    readonly_fields = ("date_joined", "created_at", "updated_at", "last_login")
    fieldsets = (
        (None, {"fields": ("email", "password")} ),
        ("Personal information", {"fields": ("full_name", "phone")} ),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")} ),
        ("Important dates", {"fields": ("last_login", "date_joined", "created_at", "updated_at")} ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "phone", "password1", "password2", "is_active", "is_staff"),
            },
        ),
    )
