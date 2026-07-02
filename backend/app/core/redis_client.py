import logging
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool
from redis.exceptions import NoScriptError

from app.core.config import get_settings
from app.core.lua_scripts import LUA_SCRIPTS

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_script_shas: dict[str, str] = {}


async def init_redis() -> None:
    global _pool, _script_shas

    settings = get_settings()
    _pool = ConnectionPool.from_url(
        settings.redis_url,
        max_connections=settings.redis_max_connections,
        socket_connect_timeout=settings.redis_socket_timeout,
        socket_timeout=settings.redis_socket_timeout,
        decode_responses=False,
    )

    client = aioredis.Redis(connection_pool=_pool)
    try:
        await _load_scripts(client)
        logger.info("Redis pool initialized and Lua scripts loaded")
    except Exception:
        # Don't crash startup if Redis is briefly unavailable — scripts are
        # lazy-loaded on first use via the EVALSHA/NoScriptError fallback path.
        logger.warning("Redis not reachable at startup; Lua scripts will load on first use")


async def _load_scripts(client: aioredis.Redis) -> None:
    global _script_shas
    for name, script in LUA_SCRIPTS.items():
        sha = await client.script_load(script)
        _script_shas[name] = sha
        logger.debug("Loaded Lua script '%s' → SHA %s", name, sha)


def get_redis() -> aioredis.Redis:
    if _pool is None:
        raise RuntimeError("Redis pool not initialized — call init_redis() first")
    return aioredis.Redis(connection_pool=_pool)


async def close_redis() -> None:
    global _pool
    if _pool:
        await _pool.disconnect()
        _pool = None


async def get_redis_time(client: aioredis.Redis) -> tuple[int, int]:
    """Return (seconds, microseconds) from Redis TIME — never use server clock."""
    result = await client.time()
    return int(result[0]), int(result[1])


async def evalsha_with_fallback(
    client: aioredis.Redis,
    algorithm: str,
    keys: list[str],
    args: list[Any],
) -> list[Any]:
    """Run EVALSHA; reload script and retry once on NoScriptError."""
    if algorithm not in LUA_SCRIPTS:
        raise ValueError(f"Unknown algorithm: {algorithm}")

    sha = _script_shas.get(algorithm)
    if sha is None:
        # Not preloaded (e.g. Redis was down at startup) — load it now.
        sha = await client.script_load(LUA_SCRIPTS[algorithm])
        _script_shas[algorithm] = sha

    try:
        return await client.evalsha(sha, len(keys), *keys, *args)
    except NoScriptError:
        logger.warning("Script cache miss for '%s', reloading", algorithm)
        script = LUA_SCRIPTS[algorithm]
        sha = await client.script_load(script)
        _script_shas[algorithm] = sha
        return await client.evalsha(sha, len(keys), *keys, *args)
