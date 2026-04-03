"""
Wagtail + Couchbase example project settings.

All secrets are read from environment variables.
Copy .env.example to .env and edit for your setup.
"""

import os

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-not-for-production")

DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1")

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")

# --- Couchbase Database Backend ---
DATABASES = {
    "default": {
        "ENGINE": "django_couchbase_orm.db.backends.couchbase",
        "NAME": os.environ.get("CB_BUCKET", "mybucket"),
        "USER": os.environ.get("CB_USERNAME", "Administrator"),
        "PASSWORD": os.environ.get("CB_PASSWORD", "password"),
        "HOST": os.environ.get("CB_HOST", "couchbase://localhost"),
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
    # Your app
    "home",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
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
        "DIRS": [],
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

USE_TZ = False
