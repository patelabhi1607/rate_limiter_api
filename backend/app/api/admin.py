import asyncio
import hashlib
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis_client import get_redis
from app.db.models import AuditLog, Blacklist, RateLimitRule, Whitelist
from app.db.session import get_db
from app.schemas.audit import AuditLogResponse, AuditQueryParams
from app.schemas.rule import (
    BlacklistCreate,
    BlacklistResponse,
    ListResponse,
    RateLimitRuleCreate,
    RateLimitRulePatch,
    RateLimitRuleResponse,
    RateLimitRuleUpdate,
    WhitelistBlacklistCreate,
    WhitelistBlacklistResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"])
_admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=True)


def _require_admin(key: str = Security(_admin_key_header)) -> None:
    settings = get_settings()
    if not secrets.compare_digest(key, settings.admin_api_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")


async def _invalidate_rule_cache() -> None:
    try:
        redis_client = get_redis()
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match="rl:rules:cache:*", count=100)
            if keys:
                await redis_client.delete(*keys)
            if cursor == 0:
                break
    except Exception:
        pass


# ── Rules ────────────────────────────────────────────────────────────────────

@router.post("/rules", response_model=RateLimitRuleResponse, status_code=201,
             dependencies=[Depends(_require_admin)])
async def create_rule(body: RateLimitRuleCreate, db: AsyncSession = Depends(get_db)):
    rule = RateLimitRule(**body.model_dump())
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    asyncio.create_task(_invalidate_rule_cache())
    return rule


@router.get("/rules", response_model=ListResponse, dependencies=[Depends(_require_admin)])
async def list_rules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count()).select_from(RateLimitRule))).scalar_one()
    rows = (
        await db.execute(
            select(RateLimitRule)
            .order_by(RateLimitRule.priority.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return ListResponse(items=rows, total=total, page=page, page_size=page_size)


@router.get("/rules/{rule_id}", response_model=RateLimitRuleResponse,
            dependencies=[Depends(_require_admin)])
async def get_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    rule = await db.get(RateLimitRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.put("/rules/{rule_id}", response_model=RateLimitRuleResponse,
            dependencies=[Depends(_require_admin)])
async def update_rule(rule_id: int, body: RateLimitRuleUpdate, db: AsyncSession = Depends(get_db)):
    rule = await db.get(RateLimitRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    for k, v in body.model_dump().items():
        setattr(rule, k, v)
    await db.flush()
    await db.refresh(rule)
    asyncio.create_task(_invalidate_rule_cache())
    return rule


@router.patch("/rules/{rule_id}", response_model=RateLimitRuleResponse,
              dependencies=[Depends(_require_admin)])
async def patch_rule(rule_id: int, body: RateLimitRulePatch, db: AsyncSession = Depends(get_db)):
    rule = await db.get(RateLimitRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(rule, k, v)
    await db.flush()
    await db.refresh(rule)
    asyncio.create_task(_invalidate_rule_cache())
    return rule


@router.delete("/rules/{rule_id}", status_code=204, dependencies=[Depends(_require_admin)])
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    rule = await db.get(RateLimitRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    asyncio.create_task(_invalidate_rule_cache())


@router.post("/rules/{rule_id}/disable", response_model=RateLimitRuleResponse,
             dependencies=[Depends(_require_admin)])
async def disable_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    rule = await db.get(RateLimitRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.enabled = False
    await db.flush()
    await db.refresh(rule)
    asyncio.create_task(_invalidate_rule_cache())
    return rule


@router.post("/rules/{rule_id}/enable", response_model=RateLimitRuleResponse,
             dependencies=[Depends(_require_admin)])
async def enable_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    rule = await db.get(RateLimitRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.enabled = True
    await db.flush()
    await db.refresh(rule)
    asyncio.create_task(_invalidate_rule_cache())
    return rule


# ── Counters ─────────────────────────────────────────────────────────────────

@router.delete("/counters/{client_id}", status_code=204, dependencies=[Depends(_require_admin)])
async def reset_counters(client_id: str):
    """Delete all Redis counters for a client. Uses SCAN — never KEYS."""
    redis_client = get_redis()
    pattern = f"rl:*:{client_id}:*"
    cursor = 0
    deleted = 0
    while True:
        cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)
        if keys:
            await redis_client.delete(*keys)
            deleted += len(keys)
        if cursor == 0:
            break
    return {"deleted": deleted}


@router.get("/quota/{client_id}", dependencies=[Depends(_require_admin)])
async def get_quota(client_id: str):
    """View current Redis keys for a client without modifying them."""
    redis_client = get_redis()
    pattern = f"rl:*:{client_id}:*"
    cursor = 0
    keys = []
    while True:
        cursor, batch = await redis_client.scan(cursor, match=pattern, count=100)
        keys.extend([k.decode() if isinstance(k, bytes) else k for k in batch])
        if cursor == 0:
            break
    return {"client_id": client_id, "active_keys": keys, "count": len(keys)}


# ── Whitelist ─────────────────────────────────────────────────────────────────

@router.post("/whitelist", response_model=WhitelistBlacklistResponse, status_code=201,
             dependencies=[Depends(_require_admin)])
async def add_whitelist(body: WhitelistBlacklistCreate, db: AsyncSession = Depends(get_db)):
    entry = Whitelist(**body.model_dump())
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    redis_client = get_redis()
    await redis_client.set(f"rl:whitelist:{body.value}", 1)
    return entry


@router.get("/whitelist", response_model=list[WhitelistBlacklistResponse],
            dependencies=[Depends(_require_admin)])
async def list_whitelist(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Whitelist))).scalars().all()
    return rows


@router.delete("/whitelist/{entry_id}", status_code=204, dependencies=[Depends(_require_admin)])
async def remove_whitelist(entry_id: int, db: AsyncSession = Depends(get_db)):
    entry = await db.get(Whitelist, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Whitelist entry not found")
    redis_client = get_redis()
    await redis_client.delete(f"rl:whitelist:{entry.value}")
    await db.delete(entry)


# ── Blacklist ─────────────────────────────────────────────────────────────────

@router.post("/blacklist", response_model=BlacklistResponse, status_code=201,
             dependencies=[Depends(_require_admin)])
async def add_blacklist(body: BlacklistCreate, db: AsyncSession = Depends(get_db)):
    entry = Blacklist(**body.model_dump())
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    redis_client = get_redis()
    if body.expires_at:
        import time
        ttl = max(1, int(body.expires_at.timestamp() - time.time()))
        await redis_client.setex(f"rl:blacklist:{body.value}", ttl, 1)
    else:
        await redis_client.set(f"rl:blacklist:{body.value}", 1)
    return entry


@router.get("/blacklist", response_model=list[BlacklistResponse],
            dependencies=[Depends(_require_admin)])
async def list_blacklist(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Blacklist))).scalars().all()
    return rows


@router.delete("/blacklist/{entry_id}", status_code=204, dependencies=[Depends(_require_admin)])
async def remove_blacklist(entry_id: int, db: AsyncSession = Depends(get_db)):
    entry = await db.get(Blacklist, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Blacklist entry not found")
    redis_client = get_redis()
    await redis_client.delete(f"rl:blacklist:{entry.value}")
    await db.delete(entry)


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/audit", response_model=list[AuditLogResponse], dependencies=[Depends(_require_admin)])
async def get_audit_log(
    client_ip: Optional[str] = None,
    route: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime
    stmt = select(AuditLog).order_by(AuditLog.timestamp.desc())
    if client_ip:
        stmt = stmt.where(AuditLog.client_ip == client_ip)
    if route:
        stmt = stmt.where(AuditLog.route == route)
    if start_time:
        stmt = stmt.where(AuditLog.timestamp >= datetime.fromisoformat(start_time))
    if end_time:
        stmt = stmt.where(AuditLog.timestamp <= datetime.fromisoformat(end_time))
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()
    return rows
