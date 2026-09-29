from django.shortcuts import render


def home(request):
    """Render the Phase 1 storefront foundation."""
    return render(request, "core/home.html")
