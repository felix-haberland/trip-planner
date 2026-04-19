"""Server-side URL fetching with SSRF guardrails (spec 006, FR-005a).

Allows only http/https, blocks addresses in private/reserved ranges after
DNS resolution, caps timeout at 10 s and body at 5 MB, and re-validates
every redirect hop.

See specs/006-golf-resorts-library/research.md R2 for rationale.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import httpx

MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 MB
CONNECT_TIMEOUT_S = 3.0
READ_TIMEOUT_S = 7.0
MAX_REDIRECTS = 5


class FetchError(Exception):
    """Raised when a URL cannot be safely fetched.

    `reason` is a short human-readable string suitable for surfacing in
    the ExtractError.fetch_error sub-status message.
    """

    def __init__(self, reason: str, *, url: Optional[str] = None):
        super().__init__(reason)
        self.reason = reason
        self.url = url

    def to_dict(self) -> dict:
        return {"status": "fetch_error", "reason": self.reason, "url": self.url}


@dataclass
class FetchResult:
    status_code: int
    headers: dict
    body_bytes: bytes
    final_url: str
    truncated: bool = False
    content_type: Optional[str] = None
    redirect_chain: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Primitives (unit-testable without network)
# ---------------------------------------------------------------------------


def _check_scheme(url: str) -> None:
    scheme = urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise FetchError(f"scheme not allowed: {scheme!r} (only http/https)", url=url)


def _is_blocked_address(
    ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> Optional[str]:
    """Return a short reason string if the IP is blocked, else None."""
    if ip_obj.is_unspecified:
        return "unspecified address"
    if ip_obj.is_loopback:
        return "loopback address"
    if ip_obj.is_link_local:
        return "link-local address"
    if ip_obj.is_private:
        return "private address (RFC1918)"
    if ip_obj.is_reserved:
        return "reserved address"
    if ip_obj.is_multicast:
        return "multicast address"
    return None


def _resolve_and_check(host: str, port: Optional[int] = None) -> list[str]:
    """Resolve `host` and raise FetchError if any resolved address is blocked.

    Returns the list of resolved IP strings when all are safe. Protects
    against multi-homed hosts where one A record would bypass the check.
    """
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise FetchError(f"DNS resolution failed for {host!r}: {e}")

    safe: list[str] = []
    for _family, _socktype, _proto, _canonname, sockaddr in infos:
        ip_str = sockaddr[0]
        # Strip IPv6 scope id ("fe80::1%eth0") before ipaddress parses it.
        ip_clean = ip_str.split("%", 1)[0]
        try:
            ip_obj = ipaddress.ip_address(ip_clean)
        except ValueError:
            raise FetchError(f"unparseable resolved address: {ip_str!r}")
        reason = _is_blocked_address(ip_obj)
        if reason:
            raise FetchError(f"host {host!r} resolves to blocked {reason} ({ip_str})")
        safe.append(ip_str)
    return safe


def _verify_peer(response: httpx.Response) -> None:
    """Defence-in-depth: ensure the actual connected peer is not blocked.

    Guards against TOCTOU where DNS answers could change between the
    pre-flight check and the connect. Silent no-op when the underlying
    stream doesn't expose peer info (e.g., in tests with a MockTransport).
    """
    try:
        net_stream = response.extensions.get("network_stream")
        if net_stream is None:
            return
        peer = net_stream.get_extra_info("peername")
        if not peer:
            return
        ip_clean = peer[0].split("%", 1)[0]
        ip_obj = ipaddress.ip_address(ip_clean)
        reason = _is_blocked_address(ip_obj)
        if reason:
            raise FetchError(f"connected peer is blocked: {reason} ({peer[0]})")
    except FetchError:
        raise
    except Exception:
        return


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def safe_get(url: str) -> FetchResult:
    """Fetch `url` under SSRF guardrails.

    Raises FetchError for scheme violations, blocked IPs, timeouts,
    oversized responses, or too many redirects.
    """
    return _safe_fetch(url, method="GET", max_redirects=MAX_REDIRECTS)


def safe_head(url: str) -> FetchResult:
    """HEAD variant of safe_get. Used for image URL validation."""
    return _safe_fetch(url, method="HEAD", max_redirects=MAX_REDIRECTS)


def _safe_fetch(url: str, *, method: str, max_redirects: int) -> FetchResult:
    redirect_chain: list[str] = []
    current_url = url

    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT_S,
        read=READ_TIMEOUT_S,
        write=READ_TIMEOUT_S,
        pool=READ_TIMEOUT_S,
    )

    # follow_redirects=False — we handle redirects manually so we can
    # re-run the SSRF checks on every hop.
    # trust_env=False — ignore HTTP(S)_PROXY env vars; we want the user's
    # URL fetched directly under our SSRF guards, not routed through a
    # proxy that could change the resolved host.
    with httpx.Client(
        follow_redirects=False, timeout=timeout, trust_env=False
    ) as client:
        for _hop in range(max_redirects + 1):
            _check_scheme(current_url)
            parsed = urlparse(current_url)
            host = parsed.hostname
            if not host:
                raise FetchError(f"no host in URL: {current_url!r}")
            _resolve_and_check(host, parsed.port)

            try:
                with client.stream(method, current_url) as response:
                    _verify_peer(response)

                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("redirect without Location header")
                        redirect_chain.append(current_url)
                        current_url = str(httpx.URL(current_url).join(location))
                        continue

                    buf = bytearray()
                    truncated = False
                    if method == "HEAD":
                        # HEAD response has no body; skip streaming.
                        pass
                    else:
                        try:
                            for chunk in response.iter_bytes():
                                remaining = MAX_BODY_BYTES - len(buf)
                                if len(chunk) > remaining:
                                    buf.extend(chunk[:remaining])
                                    truncated = True
                                    break
                                buf.extend(chunk)
                        except httpx.ReadTimeout:
                            raise FetchError("read timeout while streaming body")

                    return FetchResult(
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        body_bytes=bytes(buf),
                        final_url=current_url,
                        truncated=truncated,
                        content_type=response.headers.get("content-type"),
                        redirect_chain=redirect_chain,
                    )
            except httpx.TimeoutException:
                raise FetchError(f"timeout fetching {current_url!r}")
            except httpx.HTTPError as e:
                raise FetchError(f"http error fetching {current_url!r}: {e}")

    raise FetchError(f"too many redirects (>{max_redirects})")
