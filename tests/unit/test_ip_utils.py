import pytest
from unittest.mock import MagicMock

from app.core.ip_utils import normalize_ip, extract_client_ip


def make_request(xff: str = "", remote_host: str = "1.2.3.4", hops: int = 1):
    from unittest.mock import patch
    req = MagicMock()
    req.headers = {"X-Forwarded-For": xff} if xff else {}
    req.client = MagicMock()
    req.client.host = remote_host

    with patch("app.core.ip_utils.get_settings") as mock_settings:
        mock_settings.return_value.trusted_proxy_hops = hops
        ip = extract_client_ip(req)
    return ip


@pytest.mark.unit
class TestNormalizeIp:
    def test_plain_ipv4(self):
        assert normalize_ip("1.2.3.4") == "1.2.3.4"

    def test_ipv4_mapped_ipv6(self):
        assert normalize_ip("::ffff:1.2.3.4") == "1.2.3.4"

    def test_plain_ipv6(self):
        result = normalize_ip("2001:db8::1")
        assert "2001" in result

    def test_invalid_returns_stripped(self):
        assert normalize_ip("  not-an-ip  ") == "not-an-ip"

    def test_leading_trailing_spaces(self):
        assert normalize_ip("  192.168.1.1  ") == "192.168.1.1"


@pytest.mark.unit
class TestExtractClientIp:
    def test_no_xff_uses_remote(self):
        ip = make_request(xff="", remote_host="10.0.0.1", hops=1)
        assert ip == "10.0.0.1"

    def test_xff_single_proxy(self):
        ip = make_request(xff="203.0.113.1, 10.0.0.1", hops=1)
        assert ip == "203.0.113.1"

    def test_xff_two_proxies(self):
        ip = make_request(xff="203.0.113.1, 10.0.0.2, 10.0.0.3", hops=2)
        assert ip == "203.0.113.1"

    def test_zero_hops_uses_remote_host(self):
        ip = make_request(xff="203.0.113.1", remote_host="10.0.0.5", hops=0)
        assert ip == "10.0.0.5"

    def test_spoofed_xff_only_trust_rightmost(self):
        # Attacker injects extra IPs on the left; we trust only 1 hop from right
        ip = make_request(xff="attacker_ip, 203.0.113.1, 10.0.0.1", hops=1)
        assert ip == "203.0.113.1"

    def test_ipv4_mapped_in_xff(self):
        ip = make_request(xff="::ffff:1.2.3.4, 10.0.0.1", hops=1)
        assert ip == "1.2.3.4"
