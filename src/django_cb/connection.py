import threading
from datetime import timedelta
from typing import Any

from django.conf import settings

from django_cb.exceptions import ConnectionError

_connections: dict[str, Any] = {}
_lock = threading.RLock()


def _get_config(alias: str = "default") -> dict:
    """Retrieve Couchbase configuration for the given alias from Django settings."""
    couchbase_settings = getattr(settings, "COUCHBASE", None)
    if couchbase_settings is None:
        raise ConnectionError("COUCHBASE setting is not defined in Django settings.")
    if alias not in couchbase_settings:
        raise ConnectionError(f"Couchbase alias '{alias}' is not defined in COUCHBASE settings.")
    config = couchbase_settings[alias]
    required_keys = ("CONNECTION_STRING", "USERNAME", "PASSWORD", "BUCKET")
    missing = [k for k in required_keys if k not in config]
    if missing:
        raise ConnectionError(f"Missing required Couchbase settings for alias '{alias}': {', '.join(missing)}")
    return config


def get_cluster(alias: str = "default"):
    """Get or create a cached Cluster instance for the given alias.

    Thread-safe with lazy initialization.
    """
    cache_key = f"cluster:{alias}"
    if cache_key in _connections:
        return _connections[cache_key]

    with _lock:
        # Double-check after acquiring lock
        if cache_key in _connections:
            return _connections[cache_key]

        from couchbase.auth import PasswordAuthenticator
        from couchbase.cluster import Cluster
        from couchbase.options import ClusterOptions, ClusterTimeoutOptions

        config = _get_config(alias)

        authenticator = PasswordAuthenticator(config["USERNAME"], config["PASSWORD"])

        timeout_config = config.get("OPTIONS", {}).get("timeout_options", {})
        timeout_kwargs = {}
        if "kv_timeout" in timeout_config:
            timeout_kwargs["kv_timeout"] = timedelta(seconds=timeout_config["kv_timeout"])
        if "query_timeout" in timeout_config:
            timeout_kwargs["query_timeout"] = timedelta(seconds=timeout_config["query_timeout"])

        cluster_opts = ClusterOptions(
            authenticator,
            timeout_options=ClusterTimeoutOptions(**timeout_kwargs) if timeout_kwargs else None,
        )

        # Apply WAN development profile for Capella (TLS) connections
        if config["CONNECTION_STRING"].startswith("couchbases://"):
            cluster_opts.apply_profile("wan_development")

        cluster = Cluster.connect(config["CONNECTION_STRING"], cluster_opts)

        wait_timeout = config.get("OPTIONS", {}).get("wait_until_ready_timeout", 20)
        cluster.wait_until_ready(timedelta(seconds=wait_timeout))

        _connections[cache_key] = cluster
        return cluster


def get_bucket(alias: str = "default"):
    """Get the Bucket instance for the given alias."""
    cache_key = f"bucket:{alias}"
    if cache_key in _connections:
        return _connections[cache_key]

    with _lock:
        if cache_key in _connections:
            return _connections[cache_key]

        config = _get_config(alias)
        cluster = get_cluster(alias)
        bucket = cluster.bucket(config["BUCKET"])
        _connections[cache_key] = bucket
        return bucket


def get_collection(alias: str = "default", scope: str | None = None, collection: str | None = None):
    """Get a Collection instance.

    Args:
        alias: The Couchbase connection alias from Django settings.
        scope: The scope name. Defaults to the configured scope or '_default'.
        collection: The collection name. Defaults to '_default'.
    """
    config = _get_config(alias)
    scope_name = scope or config.get("SCOPE", "_default")
    collection_name = collection or "_default"

    cache_key = f"collection:{alias}:{scope_name}:{collection_name}"
    if cache_key in _connections:
        return _connections[cache_key]

    with _lock:
        if cache_key in _connections:
            return _connections[cache_key]

        bucket = get_bucket(alias)
        scope_obj = bucket.scope(scope_name)
        coll = scope_obj.collection(collection_name)
        _connections[cache_key] = coll
        return coll


def close_connections():
    """Close all cached cluster connections and clear the cache."""
    with _lock:
        for key in list(_connections.keys()):
            if key.startswith("cluster:"):
                try:
                    _connections[key].close()
                except Exception:
                    pass
        _connections.clear()


def reset_connections():
    """Reset the connection cache. Useful for testing."""
    with _lock:
        _connections.clear()
