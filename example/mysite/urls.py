from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    # Auth (login/logout for OIDC flow)
    path("accounts/", include("django.contrib.auth.urls")),
    # OIDC provider
    path("o/", include("oauth2_provider.urls", namespace="oauth2_provider")),
    # Static pages
    path("privacy/", TemplateView.as_view(template_name="privacy.html"), name="privacy"),
    # Beer app (API + web UI)
    path("", include("beers.urls")),
    # Wagtail catch-all (must be last)
    path("", include(wagtail_urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
