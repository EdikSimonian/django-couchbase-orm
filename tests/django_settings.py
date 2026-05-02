"""Minimal Django settings for running tests."""

import os

SECRET_KEY = "test-secret-key-not-for-production"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django_couchbase_orm",
    "tests.testapp",
]

# Add Wagtail apps if available (for wagtail_crud integration tests)
try:
    import wagtail  # noqa: F401

    INSTALLED_APPS += [
        "taggit",
        "modelcluster",
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
        "tests.wagtailapp",
    ]
    WAGTAILADMIN_BASE_URL = "http://localhost:8000"
except ImportError:
    pass

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
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

ROOT_URLCONF = "tests.test_backend_urls"

# Our migrations package is for the Document API framework, not Django's migration system
MIGRATION_MODULES = {
    "django_couchbase_orm": None,
}
STATIC_URL = "/static/"
USE_TZ = False
WAGTAIL_SITE_NAME = "Test Site"

# Document API config
COUCHBASE = {
    "default": {
        "CONNECTION_STRING": os.environ.get("CB_CONNECTION_STRING", "couchbase://localhost"),
        "USERNAME": os.environ.get("CB_USERNAME", "Administrator"),
        "PASSWORD": os.environ.get("CB_PASSWORD", "password"),
        "BUCKET": os.environ.get("CB_BUCKET", "testbucket"),
        "SCOPE": os.environ.get("CB_SCOPE", "_default"),
    }
}

# DB Backend config
DATABASES = {
    "default": {
        "ENGINE": "django_couchbase_orm.db.backends.couchbase",
        "NAME": os.environ.get("CB_BUCKET", "testbucket"),
        "USER": os.environ.get("CB_USERNAME", "Administrator"),
        "PASSWORD": os.environ.get("CB_PASSWORD", "password"),
        "HOST": os.environ.get("CB_CONNECTION_STRING", "couchbase://localhost"),
        "OPTIONS": {
            "SCOPE": os.environ.get("CB_SCOPE", "_default"),
            # Wagtail's tree-management migrations issue SELECTs whose column
            # references include reserved words like `path`, which N1QL rejects
            # with error 3000. Tests need migrate to complete so collections
            # exist, so opt the test harness into the legacy fail-soft behavior.
            # Library default remains fail-closed; production users opt in only
            # if their migrations rely on this.
            "GRACEFUL_QUERY_ERRORS": True,
        },
    }
}

DEFAULT_AUTO_FIELD = "django_couchbase_orm.db.backends.couchbase.fields.CouchbaseAutoField"
