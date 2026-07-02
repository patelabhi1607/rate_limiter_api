import asyncio
import fnmatch
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis
from jose import jwt
from prometheus_client import Counter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.algorithms.base import RateLimitResult
from app.algorithms.fixed_window import FixedWindowLimiter
from app.algorithms.leaky_bucket import LeakyBucketLimiter
from app.algorithms.sliding_window import SlidingWindowLimiter
from app.algorithms.token_bucket import TokenBucketLimiter
from app.core.config import get_settings
from app.core.ip_utils import extract_client_ip
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

_requests_counter = Counter(
    "rate_limit_requests_total",
    "Total rate-limited requests",
    ["route", "result"],
)
_redis_errors_counter = Counter(
    "rate_limit_redis_errors_total",
    "Total Redis errors during rate limiting",
)

ALGORITHM_MAP = {
    "fixed_window": FixedWindowLimiter,
    "sliding_window": SlidingWindowLimiter,
    "token_bucket": TokenBucketLimiter,
    "leaky_bucket": LeakyBucketLimiter,
}

_RULE_CACHE_TTL = 30  # seconds


def _build_redis_key(dimension: str, identifier: str, route_pattern: str, algorithm: str) -> str:
    return f"rl:{algorithm}:{dimension}:{identifier}:{route_pattern}"


def _extract_user_id(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    try:
        payload = jwt.decode(token, "", options={"verify_signature": False})
        return str(payload.get("sub", ""))
    except Exception:
        return None


def _extract_api_key(request: Request) -> Optional[str]:
    return request.headers.get("X-API-Key")


async def _get_rules(redis_client: aioredis.Redis, path: str) -> list[dict]:
    """Fetch matching rules from Redis cache, falling back to DB."""
    import hashlib
    cache_key = f"rl:rules:cache:{hashlib.md5(path.encode()).hexdigest()}"
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # Import here to avoid circular imports
    from app.db.session import get_session_factory
    from app.db.models import RateLimitRule
    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(RateLimitRule)
            .where(RateLimitRule.enabled == True)
            .order_by(RateLimitRule.priority.desc())
        )
        rows = (await session.execute(stmt)).scalars().all()
        rules = [
            {
                "id": r.id,
                "route_pattern": r.route_pattern,
                "method": r.method,
                "algorithm": r.algorithm,
                "limit": r.limit,
                "window_seconds": r.window_seconds,
                "burst_multiplier": r.burst_multiplier,
                "dimension": r.dimension,
                "tier_limits": r.tier_limits,
            }
            for r in rows
            if fnmatch.fnmatch(path, r.route_pattern)
        ]

    await redis_client.setex(cache_key, _RULE_CACHE_TTL, json.dumps(rules))
    return rules


async def _log_violation(
    client_ip: str,
    user_id: Optional[str],
    api_key: Optional[str],
    route: str,
    method: str,
    rule_id: Optional[int],
    limit: int,
    current: int,
) -> None:
    from app.db.session import get_session_factory
    from app.db.models import AuditLog

    try:
        factory = get_session_factory()
        async with factory() as session:
            log = AuditLog(
                timestamp=datetime.now(timezone.utc),
                client_ip=client_ip,
                user_id=user_id,
                api_key=api_key,
                route=route,
                method=method,
                rule_id=rule_id,
                limit_type="rate_limit",
                limit_value=limit,
                current_count=current,
            )
            session.add(log)
            await session.commit()
    except Exception:
        logger.exception("Failed to write audit log")


def _attach_headers(response: Response, result: RateLimitResult, limit: int, window: int) -> None:
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(max(0, result.remaining))
    response.headers["X-RateLimit-Reset"] = str(result.reset_at)
    # IETF draft format: "<limit>;w=<window_seconds>"
    response.headers["X-RateLimit-Policy"] = f"{limit};w={window}"
    if not result.allowed and result.retry_after > 0:
        response.headers["X-RateLimit-Retry-After"] = str(result.retry_after)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        path = request.url.path

        # Skip rate limiting for the dashboard root and internal/system paths.
        # "/" is matched exactly (a prefix check on "/" would skip everything).
        if path == "/" or any(path.startswith(skip) for skip in settings.skip_paths):
            return await call_next(request)

        client_ip = extract_client_ip(request)
        user_id = _extract_user_id(request)
        api_key = _extract_api_key(request)

        # Blacklist check (static config)
        blacklisted = settings.get_blacklist_ips()
        if client_ip in blacklisted or (api_key and api_key in blacklisted):
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden", "reason": "blacklisted"},
            )

        # Whitelist check (static config) — skip rate limiting entirely
        whitelisted = settings.get_whitelist_ips()
        if client_ip in whitelisted or (api_key and api_key in whitelisted):
            return await call_next(request)

        try:
            redis_client = get_redis()

            # DB-backed blacklist/whitelist check
            bl_key = f"rl:blacklist:{client_ip}"
            if await redis_client.exists(bl_key):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Forbidden", "reason": "blacklisted"},
                )
            wl_key = f"rl:whitelist:{client_ip}"
            if await redis_client.exists(wl_key):
                return await call_next(request)

            rules = await _get_rules(redis_client, path)

            if not rules:
                # No matching rule — apply global default
                rules = [
                    {
                        "id": None,
                        "route_pattern": "*",
                        "method": None,
                        "algorithm": settings.default_algorithm,
                        "limit": settings.default_limit,
                        "window_seconds": settings.default_window_seconds,
                        "burst_multiplier": 1.0,
                        "dimension": "ip",
                        "tier_limits": None,
                    }
                ]

            # First matching rule (sorted by priority desc) wins
            for rule in rules:
                if rule["method"] and rule["method"] != request.method:
                    continue

                algorithm = rule["algorithm"]
                limit = rule["limit"]
                window = rule["window_seconds"]
                burst = rule["burst_multiplier"]
                dimension = rule["dimension"]

                # Resolve limit from tier if applicable
                tier_limits = rule.get("tier_limits") or {}
                if tier_limits and user_id:
                    user_tier = request.headers.get("X-User-Tier", "free")
                    limit = tier_limits.get(user_tier, limit)

                if dimension == "ip":
                    identifier = client_ip
                elif dimension == "user_id":
                    identifier = user_id or client_ip
                elif dimension == "api_key":
                    identifier = api_key or client_ip
                else:  # global
                    identifier = "global"

                redis_key = _build_redis_key(dimension, identifier, rule["route_pattern"], algorithm)
                limiter_cls = ALGORITHM_MAP[algorithm]
                limiter = limiter_cls(redis_client)
                rl_result = await limiter.check(redis_key, limit, window, burst)

                _requests_counter.labels(
                    route=path, result="allowed" if rl_result.allowed else "blocked"
                ).inc()

                if not rl_result.allowed:
                    asyncio.create_task(
                        _log_violation(
                            client_ip, user_id, api_key, path, request.method,
                            rule["id"], limit, limit - rl_result.remaining,
                        )
                    )
                    resp = JSONResponse(
                        status_code=429,
                        content={
                            "detail": "Too Many Requests",
                            "retry_after": rl_result.retry_after,
                        },
                    )
                    resp.headers["Retry-After"] = str(rl_result.retry_after)
                    _attach_headers(resp, rl_result, limit, window)
                    return resp

                response = await call_next(request)
                _attach_headers(response, rl_result, limit, window)
                return response

        except Exception as exc:
            _redis_errors_counter.inc()
            logger.error("Rate limiter error: %s", exc)
            if settings.redis_fail_open:
                return await call_next(request)
            return JSONResponse(
                status_code=503,
                content={"detail": "Rate limiter unavailable"},
            )

        return await call_next(request)
