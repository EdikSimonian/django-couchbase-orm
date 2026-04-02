import logging
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class DjangoCouchbaseOrmConfig(AppConfig):
    name = "django_couchbase_orm"
    verbose_name = "Django Couchbase ORM"
    default_auto_field = None

    def ready(self):
        """Pre-warm Couchbase connections in a background thread on startup."""
        from django.conf import settings

        if getattr(settings, "COUCHBASE_PREWARM", True):
            thread = threading.Thread(target=self._prewarm, daemon=True)
            thread.start()

    def _prewarm(self):
        try:
            from django.conf import settings

            from django_couchbase_orm.connection import get_cluster

            couchbase_settings = getattr(settings, "COUCHBASE", {})
            for alias in couchbase_settings:
                get_cluster(alias)
                logger.info("Pre-warmed Couchbase connection: %s", alias)
        except Exception as e:
            logger.warning("Failed to pre-warm Couchbase connection: %s", e)
