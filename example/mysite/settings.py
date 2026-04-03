"""
Wagtail + Couchbase example project settings.

All secrets are read from environment variables.
Copy .env.example to .env and edit for your setup.
"""

import os

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-not-for-production")

DEBUG = os.environ.get("DJANGO_DEBUG", os.environ.get("DEBUG", "True")).lower() in ("true", "1")

ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS", os.environ.get("ALLOWED_HOSTS", "*")
).split(",")

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

# --- Couchbase Database Backend ---
DATABASES = {
    "default": {
        "ENGINE": "django_couchbase_orm.db.backends.couchbase",
        "NAME": os.environ.get("CB_BUCKET", "mybucket"),
        "USER": os.environ.get("CB_USERNAME", "Administrator"),
        "PASSWORD": os.environ.get("CB_PASSWORD", "password"),
        "HOST": os.environ.get("CB_CONNECTION_STRING", os.environ.get("CB_HOST", "couchbase://localhost")),
        "OPTIONS": {
            "SCOPE": os.environ.get("CB_SCOPE", "_default"),
        },
    }
}

DEFAULT_AUTO_FIELD = "django_couchbase_orm.db.backends.couchbase.fields.CouchbaseAutoField"

# --- Apps ---
INSTALLED_APPS = [
    # Django
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Wagtail dependencies
    "taggit",
    "modelcluster",
    # Wagtail
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    # Your apps
    "home",
    "beers",
    # API & Auth
    "rest_framework",
    "oauth2_provider",
    "corsheaders",
]

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "oauth2_provider.contrib.rest_framework.OAuth2Authentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

# --- OIDC Provider (django-oauth-toolkit) ---
OAUTH2_PROVIDER = {
    "OIDC_ENABLED": True,
    "OIDC_RSA_PRIVATE_KEY": os.environ.get("OIDC_RSA_PRIVATE_KEY", ""),
    "SCOPES": {
        "openid": "OpenID Connect",
        "profile": "User profile",
        "email": "User email",
    },
    "OIDC_USERINFO_ENDPOINT": "beers.oidc.get_claims",
    "PKCE_REQUIRED": True,
    "ACCESS_TOKEN_EXPIRE_SECONDS": 3600,
    "REFRESH_TOKEN_EXPIRE_SECONDS": 86400,
    "ROTATE_REFRESH_TOKEN": True,
    "ALLOWED_REDIRECT_URI_SCHEMES": ["https", "brewsync"],
}

# --- CORS ---
CORS_ALLOW_ALL_ORIGINS = True

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

ROOT_URLCONF = "mysite.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "mysite.wsgi.application"

# --- Wagtail ---
WAGTAIL_SITE_NAME = "My Couchbase Site"
WAGTAILADMIN_BASE_URL = os.environ.get("WAGTAILADMIN_BASE_URL", "http://localhost:8000")

# --- Static ---
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "staticfiles")

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

USE_TZ = False
