"""
Demo endpoints — each demonstrates a different algorithm or rate-limit dimension.
The middleware enforces rules defined in the DB; these endpoints just return informational responses.
"""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/demo", tags=["demo"])


def _client_info(request: Request) -> dict:
    from app.core.ip_utils import extract_client_ip
    return {
        "client_ip": extract_client_ip(request),
        "user_agent": request.headers.get("User-Agent", ""),
        "x_api_key": request.headers.get("X-API-Key", ""),
        "authorization": "present" if "Authorization" in request.headers else "absent",
    }


@router.get("/public")
async def demo_public(request: Request):
    """Per-IP, 10/min, sliding window. No auth required."""
    return {"endpoint": "public", "description": "10 req/min per IP (sliding window)", **_client_info(request)}


@router.get("/authenticated")
async def demo_authenticated(request: Request):
    """Per-user_id, 100/min, token bucket. Provide Bearer token."""
    return {"endpoint": "authenticated", "description": "100 req/min per user (token bucket)", **_client_info(request)}


@router.get("/api-key")
async def demo_api_key(request: Request):
    """Per API key, 50/min, fixed window. Provide X-API-Key header."""
    return {"endpoint": "api-key", "description": "50 req/min per API key (fixed window)", **_client_info(request)}


@router.get("/tiered")
async def demo_tiered(request: Request):
    """Tiered limits: free=5, pro=50, enterprise=500 per min. Set X-User-Tier header."""
    tier = request.headers.get("X-User-Tier", "free")
    return {"endpoint": "tiered", "tier": tier, "description": "free=5 pro=50 enterprise=500 per min", **_client_info(request)}


@router.get("/burst")
async def demo_burst(request: Request):
    """Token bucket with burst_multiplier=2.0 — allows 20 req before blocking at 10/min."""
    return {"endpoint": "burst", "description": "10/min but burst up to 20 (token bucket)", **_client_info(request)}


@router.get("/strict")
async def demo_strict(request: Request):
    """Leaky bucket — exactly 1 req/sec output rate."""
    return {"endpoint": "strict", "description": "1 req/sec leaky bucket", **_client_info(request)}
