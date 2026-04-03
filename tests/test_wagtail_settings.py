"""Django settings for testing Wagtail with the Couchbase backend."""

SECRET_KEY = "test-wagtail-secret-key"

DATABASES = {
    "default": {
        "ENGINE": "django_couchbase_orm.db.backends.couchbase",
        "NAME": "testbucket",
        "USER": "Administrator",
        "PASSWORD": "password",
        "HOST": "couchbase://localhost",
        "OPTIONS": {"SCOPE": "_default"},
        "TEST": {"NAME": "testbucket"},
    }
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
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

ROOT_URLCONF = "tests.test_wagtail_urls"
WAGTAIL_SITE_NAME = "Test Wagtail Site"
WAGTAILADMIN_BASE_URL = "http://localhost:8000"

DEFAULT_AUTO_FIELD = "django_couchbase_orm.db.backends.couchbase.fields.CouchbaseAutoField"
STATIC_URL = "/static/"
USE_TZ = False
DEBUG = True
ALLOWED_HOSTS = ["*"]
