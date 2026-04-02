"""Async connection management for Couchbase using acouchbase SDK."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

_async_connections: dict[str, Any] = {}
_async_lock = asyncio.Lock()


def _get_config(alias: str = "default") -> dict:
    """Retrieve Couchbase configuration (shared with sync module)."""
    from django_couchbase_orm.connection import _get_config as sync_get_config

    return sync_get_config(alias)


async def get_async_cluster(alias: str = "default"):
    """Get or create a cached async Cluster instance."""
    cache_key = f"cluster:{alias}"
    if cache_key in _async_connections:
        return _async_connections[cache_key]

    async with _async_lock:
        if cache_key in _async_connections:
            return _async_connections[cache_key]

        from acouchbase.cluster import AsyncCluster
        from couchbase.auth import PasswordAuthenticator
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

        if config["CONNECTION_STRING"].startswith("couchbases://"):
            cluster_opts.apply_profile("wan_development")

        cluster = await AsyncCluster.connect(config["CONNECTION_STRING"], cluster_opts)

        wait_timeout = config.get("OPTIONS", {}).get("wait_until_ready_timeout", 20)
        await cluster.wait_until_ready(timedelta(seconds=wait_timeout))

        _async_connections[cache_key] = cluster
        return cluster


async def get_async_bucket(alias: str = "default"):
    """Get the async Bucket instance."""
    cache_key = f"bucket:{alias}"
    if cache_key in _async_connections:
        return _async_connections[cache_key]

    async with _async_lock:
        if cache_key in _async_connections:
            return _async_connections[cache_key]

        config = _get_config(alias)
        cluster = await get_async_cluster(alias)
        bucket = cluster.bucket(config["BUCKET"])
        _async_connections[cache_key] = bucket
        return bucket


async def get_async_collection(alias: str = "default", scope: str | None = None, collection: str | None = None):
    """Get an async Collection instance."""
    config = _get_config(alias)
    scope_name = scope or config.get("SCOPE", "_default")
    collection_name = collection or "_default"

    cache_key = f"collection:{alias}:{scope_name}:{collection_name}"
    if cache_key in _async_connections:
        return _async_connections[cache_key]

    async with _async_lock:
        if cache_key in _async_connections:
            return _async_connections[cache_key]

        bucket = await get_async_bucket(alias)
        scope_obj = bucket.scope(scope_name)
        coll = scope_obj.collection(collection_name)
        _async_connections[cache_key] = coll
        return coll


async def close_async_connections():
    """Close all cached async cluster connections."""
    async with _async_lock:
        for key in list(_async_connections.keys()):
            if key.startswith("cluster:"):
                try:
                    _async_connections[key].close()
                except Exception:
                    pass
        _async_connections.clear()


def reset_async_connections():
    """Reset the async connection cache. Useful for testing."""
    _async_connections.clear()
