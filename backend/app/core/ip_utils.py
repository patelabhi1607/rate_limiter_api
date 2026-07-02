import ipaddress
import logging
from starlette.requests import Request

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def normalize_ip(raw: str) -> str:
    """Normalize IP string — collapse IPv4-mapped IPv6 (::ffff:1.2.3.4) to IPv4."""
    try:
        addr = ipaddress.ip_address(raw.strip())
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            return str(addr.ipv4_mapped)
        return str(addr)
    except ValueError:
        logger.warning("Invalid IP address string: %r", raw)
        return raw.strip()


def extract_client_ip(request: Request) -> str:
    """
    Extract the real client IP using trusted proxy hops.

    X-Forwarded-For: client, proxy1, proxy2
    The rightmost N entries are from trusted proxies — take the one just
    to the left of the trusted chain as the real client IP.

    TRUSTED_PROXY_HOPS=0 → trust nobody; use request.client.host directly.
    TRUSTED_PROXY_HOPS=1 → trust the immediately connecting proxy (default).
    TRUSTED_PROXY_HOPS=N → trust N rightmost entries in X-Forwarded-For.
    """
    settings = get_settings()
    hops = settings.trusted_proxy_hops

    if hops == 0:
        raw = request.client.host if request.client else "unknown"
        return normalize_ip(raw)

    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        # The rightmost `hops` entries are from trusted proxies; client is just before them
        idx = max(0, len(parts) - hops - 1)
        raw = parts[idx] if parts else (request.client.host if request.client else "unknown")
    else:
        raw = request.client.host if request.client else "unknown"

    return normalize_ip(raw)
