from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey,
    Index, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RateLimitRule(Base):
    __tablename__ = "rate_limit_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    route_pattern: Mapped[str] = mapped_column(String(256), nullable=False)
    method: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # None = all methods
    algorithm: Mapped[str] = mapped_column(String(32), nullable=False, default="sliding_window")
    limit: Mapped[int] = mapped_column(Integer, nullable=False)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    burst_multiplier: Mapped[float] = mapped_column(nullable=False, default=1.0)
    # dimension: ip | user_id | api_key | global
    dimension: Mapped[str] = mapped_column(String(32), nullable=False, default="ip")
    # tier_limits: {"free": 5, "pro": 50, "enterprise": 500} — overrides limit when dimension=user_id
    tier_limits: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="rule")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    client_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    api_key: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    route: Mapped[str] = mapped_column(String(256), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("rate_limit_rules.id", ondelete="SET NULL"), nullable=True
    )
    limit_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    limit_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    rule: Mapped[Optional["RateLimitRule"]] = relationship(back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_ip_route", "client_ip", "route"),
        Index("ix_audit_timestamp_route", "timestamp", "route"),
    )


class Whitelist(Base):
    __tablename__ = "whitelists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # ip | api_key
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Blacklist(Base):
    __tablename__ = "blacklists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # ip | api_key
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
