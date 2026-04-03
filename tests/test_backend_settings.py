"""Django settings for testing the Couchbase database backend."""

SECRET_KEY = "test-secret-key-for-backend-testing"

DATABASES = {
    "default": {
        "ENGINE": "django_couchbase_orm.db.backends.couchbase",
        "NAME": "testbucket",
        "USER": "Administrator",
        "PASSWORD": "password",
        "HOST": "couchbase://localhost",
        "OPTIONS": {
            "SCOPE": "_default",
        },
        "TEST": {
            "NAME": "testbucket",
        },
    }
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "tests.testapp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
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

DEFAULT_AUTO_FIELD = "django_couchbase_orm.db.backends.couchbase.fields.CouchbaseAutoField"

USE_TZ = False
DEBUG = True
ALLOWED_HOSTS = ["*"]
