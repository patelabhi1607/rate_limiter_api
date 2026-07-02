from fastapi import APIRouter
from sqlalchemy import text

from app.core.redis_client import get_redis
from app.db.session import get_session_factory

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    status = {"api": "ok", "redis": "unknown", "postgres": "unknown"}
    try:
        r = get_redis()
        await r.ping()
        status["redis"] = "ok"
    except Exception as e:
        status["redis"] = f"error: {e}"

    try:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        status["postgres"] = "ok"
    except Exception as e:
        status["postgres"] = f"error: {e}"

    overall = "ok" if all(v == "ok" for v in status.values()) else "degraded"
    status["status"] = overall
    return status
