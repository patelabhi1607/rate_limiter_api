from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


Algorithm = Literal["token_bucket", "sliding_window", "fixed_window", "leaky_bucket"]
Dimension = Literal["ip", "user_id", "api_key", "global"]


class RateLimitRuleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    route_pattern: str = Field(..., min_length=1, max_length=256)
    method: Optional[str] = None
    algorithm: Algorithm = "sliding_window"
    limit: int = Field(..., gt=0)
    window_seconds: int = Field(..., gt=0)
    burst_multiplier: float = Field(1.0, ge=1.0, le=10.0)
    dimension: Dimension = "ip"
    tier_limits: Optional[dict[str, int]] = None
    enabled: bool = True
    priority: int = 0

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"method must be one of {allowed} or null")
        return upper


class RateLimitRuleCreate(RateLimitRuleBase):
    pass


class RateLimitRuleUpdate(RateLimitRuleBase):
    pass


class RateLimitRulePatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    route_pattern: Optional[str] = Field(None, min_length=1, max_length=256)
    method: Optional[str] = None
    algorithm: Optional[Algorithm] = None
    limit: Optional[int] = Field(None, gt=0)
    window_seconds: Optional[int] = Field(None, gt=0)
    burst_multiplier: Optional[float] = Field(None, ge=1.0, le=10.0)
    dimension: Optional[Dimension] = None
    tier_limits: Optional[dict[str, int]] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None


class RateLimitRuleResponse(RateLimitRuleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ListResponse(BaseModel):
    items: list[RateLimitRuleResponse]
    total: int
    page: int
    page_size: int


class WhitelistBlacklistCreate(BaseModel):
    value: str = Field(..., min_length=1, max_length=256)
    type: Literal["ip", "api_key"]
    reason: Optional[str] = None


class WhitelistBlacklistResponse(WhitelistBlacklistCreate):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class BlacklistCreate(WhitelistBlacklistCreate):
    expires_at: Optional[datetime] = None


class BlacklistResponse(BlacklistCreate):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}
