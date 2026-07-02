"""
Seed the demo rate-limit rules so the interactive dashboard actually
enforces the limits it advertises. Idempotent — safe to run on every startup.
"""
import logging

from sqlalchemy import select

from app.db.models import RateLimitRule
from app.db.session import get_session_factory

logger = logging.getLogger(__name__)

DEMO_RULES = [
    {
        "name": "demo-public",
        "route_pattern": "/demo/public",
        "algorithm": "sliding_window",
        "limit": 10,
        "window_seconds": 60,
        "dimension": "ip",
        "priority": 100,
    },
    {
        "name": "demo-authenticated",
        "route_pattern": "/demo/authenticated",
        "algorithm": "token_bucket",
        "limit": 100,
        "window_seconds": 60,
        "dimension": "user_id",
        "priority": 100,
    },
    {
        "name": "demo-api-key",
        "route_pattern": "/demo/api-key",
        "algorithm": "fixed_window",
        "limit": 50,
        "window_seconds": 60,
        "dimension": "api_key",
        "priority": 100,
    },
    {
        "name": "demo-tiered",
        "route_pattern": "/demo/tiered",
        "algorithm": "sliding_window",
        "limit": 5,
        "window_seconds": 60,
        "dimension": "user_id",
        "tier_limits": {"free": 5, "pro": 50, "enterprise": 500},
        "priority": 100,
    },
    {
        "name": "demo-burst",
        "route_pattern": "/demo/burst",
        "algorithm": "token_bucket",
        "limit": 10,
        "window_seconds": 60,
        "burst_multiplier": 2.0,
        "dimension": "ip",
        "priority": 100,
    },
    {
        "name": "demo-strict",
        "route_pattern": "/demo/strict",
        "algorithm": "leaky_bucket",
        "limit": 1,
        "window_seconds": 1,
        "dimension": "ip",
        "priority": 100,
    },
]


async def seed_demo_rules() -> None:
    try:
        factory = get_session_factory()
        async with factory() as session:
            existing = {
                r for r in (await session.execute(select(RateLimitRule.name))).scalars().all()
            }
            created = 0
            for spec in DEMO_RULES:
                if spec["name"] not in existing:
                    session.add(RateLimitRule(**spec))
                    created += 1
            if created:
                await session.commit()
                logger.info("Seeded %d demo rate-limit rules", created)
    except Exception:
        logger.exception("Failed to seed demo rules (DB not ready?) — continuing")
