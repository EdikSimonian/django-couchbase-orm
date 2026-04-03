from django.apps import AppConfig


class BeersConfig(AppConfig):
    default_auto_field = "django_couchbase_orm.db.backends.couchbase.fields.CouchbaseAutoField"
    name = "beers"
