"""Minimal Django settings for testing the Couchbase database backend."""

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
]

DEFAULT_AUTO_FIELD = "django_couchbase_orm.db.backends.couchbase.fields.CouchbaseAutoField"

USE_TZ = False
