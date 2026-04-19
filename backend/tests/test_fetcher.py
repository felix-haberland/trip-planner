"""Unit tests for the SSRF-guarded URL fetcher (FR-005a, research R2).

Focuses on the primitives: scheme check, IP classification, DNS-level
blocking. Integration-level redirect re-validation is covered by
inspection; a full end-to-end test would require a real HTTP server.
"""

from __future__ import annotations

import ipaddress
import socket
from unittest.mock import patch

import pytest

from app.golf.fetcher import (
    FetchError,
    _check_scheme,
    _is_blocked_address,
    _resolve_and_check,
    safe_get,
)

# ---------------------------------------------------------------------------
# Scheme allowlist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scheme", ["ftp", "file", "gopher", "javascript", "data"])
def test_blocks_non_http_schemes(scheme):
    with pytest.raises(FetchError) as exc:
        _check_scheme(f"{scheme}://example.com/path")
    assert "scheme not allowed" in exc.value.reason


def test_allows_http():
    # Should not raise.
    _check_scheme("http://example.com/")


def test_allows_https():
    _check_scheme("https://example.com/")


# ---------------------------------------------------------------------------
# IP classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ip,expected_keyword",
    [
        ("127.0.0.1", "loopback"),
        ("10.0.0.5", "private"),
        ("10.255.255.255", "private"),
        ("172.16.0.1", "private"),
        ("192.168.1.1", "private"),
        ("169.254.169.254", "link-local"),  # AWS metadata — classic SSRF target
        ("0.0.0.0", "unspecified"),
        ("::1", "loopback"),
        ("fe80::1", "link-local"),
        ("fc00::1", "private"),
        ("224.0.0.1", "multicast"),
    ],
)
def test_blocked_addresses(ip, expected_keyword):
    reason = _is_blocked_address(ipaddress.ip_address(ip))
    assert reason is not None
    assert expected_keyword in reason


@pytest.mark.parametrize(
    "ip",
    [
        "8.8.8.8",
        "1.1.1.1",
        "93.184.216.34",  # example.com
        "2606:2800:220:1:248:1893:25c8:1946",  # example.com AAAA
    ],
)
def test_public_addresses_allowed(ip):
    assert _is_blocked_address(ipaddress.ip_address(ip)) is None


# ---------------------------------------------------------------------------
# DNS-level blocking
# ---------------------------------------------------------------------------


def _fake_getaddrinfo(addr: str):
    """Factory: returns a socket.getaddrinfo stub that always resolves to `addr`."""

    def _inner(host, port, *args, **kwargs):
        # Detect IPv6 vs IPv4 to return the right family.
        try:
            ip_obj = ipaddress.ip_address(addr)
        except ValueError:
            raise socket.gaierror("fake DNS: unparseable")
        if isinstance(ip_obj, ipaddress.IPv6Address):
            return [
                (socket.AF_INET6, socket.SOCK_STREAM, 0, "", (addr, port or 0, 0, 0))
            ]
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (addr, port or 0))]

    return _inner


def test_resolve_and_check_allows_public():
    with patch(
        "app.golf.fetcher.socket.getaddrinfo", side_effect=_fake_getaddrinfo("8.8.8.8")
    ):
        result = _resolve_and_check("example.com", 443)
    assert result == ["8.8.8.8"]


@pytest.mark.parametrize(
    "private_ip", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1"]
)
def test_resolve_and_check_rejects_private(private_ip):
    with patch(
        "app.golf.fetcher.socket.getaddrinfo", side_effect=_fake_getaddrinfo(private_ip)
    ):
        with pytest.raises(FetchError) as exc:
            _resolve_and_check("sneaky.example.com", 80)
    assert "blocked" in exc.value.reason


def test_resolve_and_check_dns_failure():
    def _raise(*_a, **_kw):
        raise socket.gaierror("no such host")

    with patch("app.golf.fetcher.socket.getaddrinfo", side_effect=_raise):
        with pytest.raises(FetchError) as exc:
            _resolve_and_check("nope.invalid", 80)
    assert "DNS resolution failed" in exc.value.reason


# ---------------------------------------------------------------------------
# Public entry point — scheme + DNS short-circuits (no HTTP needed)
# ---------------------------------------------------------------------------


def test_safe_get_rejects_ftp_without_network():
    """The scheme check runs first, so no DNS is even attempted."""
    with pytest.raises(FetchError) as exc:
        safe_get("ftp://example.com/resource")
    assert "scheme" in exc.value.reason


def test_safe_get_rejects_private_ip_target():
    """URL with a literal private IP must be rejected at DNS-check stage.

    Uses the real socket.getaddrinfo (which for a literal IP address just
    echoes it back), so no mocks needed.
    """
    with pytest.raises(FetchError) as exc:
        safe_get("http://127.0.0.1:9000/admin")
    assert "blocked" in exc.value.reason
    assert "loopback" in exc.value.reason


def test_safe_get_rejects_rfc1918_target():
    with pytest.raises(FetchError) as exc:
        safe_get("http://10.0.0.5/")
    assert "blocked" in exc.value.reason


def test_safe_get_rejects_link_local_target():
    """AWS metadata endpoint style — classic SSRF target."""
    with pytest.raises(FetchError) as exc:
        safe_get("http://169.254.169.254/latest/meta-data/")
    assert "link-local" in exc.value.reason


def test_safe_get_rejects_ipv6_loopback():
    with pytest.raises(FetchError) as exc:
        safe_get("http://[::1]:8080/")
    assert "loopback" in exc.value.reason
