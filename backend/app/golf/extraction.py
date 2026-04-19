"""AI extraction pipeline for the golf library (spec 006, FR-005/006/008).

Two input paths:

1. URL — the backend pre-fetches the page via `fetcher.safe_get` and passes
   the body to Claude with a "return structured data" tool.
2. Name only — Claude is invoked with the Anthropic server-side
   `web_search_20250305` tool enabled; it searches, reads pages, and
   emits the structured return tool. The client sees a single API
   round-trip (the server auto-executes web_search).

Returns `ExtractedResort` / `ExtractedCourse` on success; raises
`ExtractError` (sub-status `api_error` / `no_match` / `fetch_error` /
`ambiguous`) on failure. No auto-retry — the UI is responsible.

See `specs/006-golf-resorts-library/research.md` R1, R4 for rationale.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import urlparse

import anthropic
import httpx

from . import fetcher, schemas
from .fetcher import (
    CONNECT_TIMEOUT_S,
    READ_TIMEOUT_S,
    _check_scheme,
    _resolve_and_check,
    _verify_peer,
)

ExtractStatus = Literal["api_error", "no_match", "fetch_error", "ambiguous"]
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 2048  # Resort/course extractions fit comfortably; keep Sonnet, trim output
BODY_CHAR_BUDGET = 50_000  # ~12k tokens — covers OG/meta/hero/first few sections
WEB_SEARCH_MAX_USES = 2  # Cut from 5 — forces Claude to commit on fewer sources
IMAGE_VALIDATE_WORKERS = 5


@dataclass
class ExtractError(Exception):
    status: ExtractStatus
    message: str
    partial_data: Optional[dict] = None
    candidates: Optional[list[dict]] = None

    def __str__(self) -> str:
        return f"{self.status}: {self.message}"


# ---------------------------------------------------------------------------
# Tool schemas — the "return extracted data" client-side tool.
#
# Kept intentionally broad (description only; we rely on Pydantic on the way
# out). Anthropic will populate block.input with a dict matching our
# GolfResortCreate / GolfCourseCreate shape.
# ---------------------------------------------------------------------------


_RESORT_TOOL = {
    "name": "extracted_resort",
    "description": (
        "Return the extracted golf resort data as a structured object. "
        "Call this exactly once when you have identified the resort and "
        "collected its metadata."
    ),
    "input_schema": {
        "type": "object",
        "required": ["name", "country_code"],
        "properties": {
            "name": {"type": "string"},
            "url": {"type": "string"},
            "country_code": {
                "type": "string",
                "description": "ISO 3166-1 alpha-2 (e.g., 'PT', 'ES', 'GB').",
            },
            "region_name_raw": {"type": "string"},
            "town": {"type": "string"},
            "latitude": {"type": "number"},
            "longitude": {"type": "number"},
            "hotel_name": {"type": "string"},
            "hotel_type": {
                "type": "string",
                "enum": ["luxury", "boutique", "golf_hotel", "none"],
            },
            "star_rating": {"type": "integer", "minimum": 0, "maximum": 5},
            "price_category": {
                "type": "string",
                "enum": [
                    "\u20ac",
                    "\u20ac\u20ac",
                    "\u20ac\u20ac\u20ac",
                    "\u20ac\u20ac\u20ac\u20ac",
                ],
            },
            "best_months": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1, "maximum": 12},
            },
            "description": {"type": "string"},
            "amenities": {"type": "array", "items": {"type": "string"}},
            "rank_rating": {"type": "integer", "minimum": 0, "maximum": 100},
            "tags": {"type": "array", "items": {"type": "string"}},
            "courses": {
                "type": "array",
                "description": (
                    "On-property courses. Each entry matches the extracted_course shape."
                ),
                "items": {"type": "object"},
            },
            "source_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "URLs you consulted during extraction (ranking articles, reviews, "
                    "official site). The official homepage URL, if distinct from the "
                    "fetched page, goes in `url` (not here)."
                ),
            },
        },
    },
}


_COURSE_TOOL = {
    "name": "extracted_course",
    "description": (
        "Return the extracted golf course data as a structured object. "
        "If the course belongs to a resort, populate possible_parent_resort "
        "but do NOT set resort_id — the backend will not auto-create the "
        "parent. Call this exactly once when ready."
    ),
    "input_schema": {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "url": {"type": "string"},
            "country_code": {"type": "string"},
            "region_name_raw": {"type": "string"},
            "town": {"type": "string"},
            "latitude": {"type": "number"},
            "longitude": {"type": "number"},
            "holes": {"type": "integer", "enum": [9, 18, 27, 36]},
            "par": {"type": "integer"},
            "length_yards": {"type": "integer"},
            "type": {
                "type": "string",
                "enum": [
                    "links",
                    "parkland",
                    "heathland",
                    "desert",
                    "coastal",
                    "mountain",
                    "other",
                ],
            },
            "architect": {"type": "string"},
            "year_opened": {"type": "integer"},
            "difficulty": {"type": "integer", "minimum": 1, "maximum": 5},
            "signature_holes": {"type": "string"},
            "description": {"type": "string"},
            "green_fee_low_eur": {"type": "integer"},
            "green_fee_high_eur": {"type": "integer"},
            "green_fee_notes": {"type": "string"},
            "best_months": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1, "maximum": 12},
            },
            "rank_rating": {"type": "integer", "minimum": 0, "maximum": 100},
            "tags": {"type": "array", "items": {"type": "string"}},
            "source_urls": {"type": "array", "items": {"type": "string"}},
            "possible_parent_resort_name": {
                "type": "string",
                "description": (
                    "If this course appears to belong to a branded resort, "
                    "set the resort's name here. The backend will check if it "
                    "exists in the library; it will NOT auto-create it."
                ),
            },
        },
    },
}


_SYSTEM_PROMPT_RESORT = (
    "You extract structured metadata about golf resorts from web sources. "
    "Be faithful to the source: do not invent rankings, prices, or amenities. "
    "When a field is not stated or cannot be confidently inferred, omit it. "
    "For price_category use four tiers (\u20ac cheapest to \u20ac\u20ac\u20ac\u20ac "
    "most expensive). For rank_rating, produce a 0\u2013100 score that reflects "
    "overall quality signals (editorial rankings, user ratings, reputation). "
    "Always call the extracted_resort tool exactly once when finished."
)


_SYSTEM_PROMPT_COURSE = (
    "You extract structured metadata about individual golf courses. "
    "Be faithful to the source; do not invent par, length, or architect. "
    "If the course belongs to a branded resort, populate "
    "possible_parent_resort_name. Always call the extracted_course tool "
    "exactly once when finished."
)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def extract_resort(
    *,
    url: Optional[str] = None,
    name: Optional[str] = None,
    extra_source_urls: Optional[list[str]] = None,
    existing_parent_resort_lookup=None,
) -> schemas.ExtractedResort:
    """Extract resort metadata.

    `extra_source_urls` are URLs to record as provenance but not fetch
    (e.g., the ranking-page URL when we pre-enumerated and the primary
    fetch target is the resort's own homepage). They are merged into the
    result's `source_urls` list.
    """
    data, source_urls, base_url = _extract(
        entity_type="resort",
        url=url,
        name=name,
        tool_def=_RESORT_TOOL,
        system_prompt=_SYSTEM_PROMPT_RESORT,
    )
    for s in extra_source_urls or []:
        if s and s not in source_urls:
            source_urls.append(s)
    return _build_resort_result(data, source_urls, base_url)


def extract_course(
    *,
    url: Optional[str] = None,
    name: Optional[str] = None,
    extra_source_urls: Optional[list[str]] = None,
    existing_parent_resort_lookup=None,
) -> schemas.ExtractedCourse:
    """Extract a single course. See `extract_resort` for parameter docs."""
    data, source_urls, base_url = _extract(
        entity_type="course",
        url=url,
        name=name,
        tool_def=_COURSE_TOOL,
        system_prompt=_SYSTEM_PROMPT_COURSE,
    )
    for s in extra_source_urls or []:
        if s and s not in source_urls:
            source_urls.append(s)
    return _build_course_result(
        data, source_urls, base_url, existing_parent_resort_lookup
    )


# ---------------------------------------------------------------------------
# Core extraction loop
# ---------------------------------------------------------------------------


def _extract(
    *,
    entity_type: str,
    url: Optional[str],
    name: Optional[str],
    tool_def: dict,
    system_prompt: str,
) -> tuple[dict, list[str], Optional[str]]:
    """Returns (tool_input, source_urls, base_url_for_relative_resolution)."""
    if not url and not name:
        raise ExtractError(
            status="no_match",
            message="Either a URL or a name must be provided.",
        )

    source_urls: list[str] = []
    base_url: Optional[str] = (
        None  # set only on URL-path; used to resolve relative img src
    )
    tools = [tool_def]
    user_content_parts: list[dict] = []

    if url:
        # Pre-fetch under SSRF guards.
        try:
            fetched = fetcher.safe_get(url)
        except fetcher.FetchError as e:
            raise ExtractError(status="fetch_error", message=e.reason)
        source_urls.append(url)
        base_url = fetched.final_url
        body_text = fetched.body_bytes.decode("utf-8", errors="ignore")
        if len(body_text) > BODY_CHAR_BUDGET:
            body_text = body_text[:BODY_CHAR_BUDGET]
        user_content_parts.append(
            {
                "type": "text",
                "text": (
                    f"Extract a {entity_type} record from this page.\n"
                    f"URL: {url}\n\n"
                    f"--- PAGE CONTENT ---\n{body_text}\n--- END PAGE CONTENT ---\n\n"
                    "Call the tool with the structured data when done."
                ),
            }
        )
    else:
        # Name-only: enable the server-side web search tool (budget trimmed).
        tools.append(
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": WEB_SEARCH_MAX_USES,
            }
        )
        user_content_parts.append(
            {
                "type": "text",
                "text": (
                    f"Identify and extract data for the {entity_type} named "
                    f"{name!r}. Use web search to find the official site and "
                    f"at least one independent source (ranking, review, etc.). "
                    "If multiple plausible matches exist, pick the most "
                    "famous/highest-rated one. If no confident match, do NOT "
                    "call the extracted tool. Call the tool with structured "
                    "data when ready."
                ),
            }
        )

    messages = [{"role": "user", "content": user_content_parts}]

    client = _get_client()
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )
    except anthropic.APITimeoutError:
        raise ExtractError(
            status="api_error", message="Claude API timed out. Please retry."
        )
    except anthropic.RateLimitError:
        raise ExtractError(
            status="api_error",
            message="Claude API rate limit reached. Please retry shortly.",
        )
    except anthropic.APIError as e:
        raise ExtractError(status="api_error", message=f"Claude API error: {e}")

    # Collect any web_search URLs as additional sources.
    for block in response.content:
        block_type = getattr(block, "type", None)
        if block_type == "web_search_tool_result":
            results = getattr(block, "content", None) or []
            for r in results:
                r_url = getattr(r, "url", None) or (
                    isinstance(r, dict) and r.get("url")
                )
                if r_url and r_url not in source_urls:
                    source_urls.append(r_url)

    # Look for our return tool.
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and getattr(
            block, "name", ""
        ) in ("extracted_resort", "extracted_course"):
            tool_input = dict(block.input)
            # Merge any source_urls the model passed with what we already collected.
            model_sources = tool_input.pop("source_urls", None) or []
            for s in model_sources:
                if s and s not in source_urls:
                    source_urls.append(s)
            return tool_input, source_urls, base_url

    # No return tool used. Distinguish name-only (no_match) from URL (ambiguous).
    if url:
        raise ExtractError(
            status="ambiguous",
            message=(
                "The page was fetched but Claude could not confidently "
                "extract a single entity from it."
            ),
        )
    raise ExtractError(
        status="no_match",
        message=(
            f"Could not identify a specific {entity_type} for {name!r}. "
            "Refine the name or provide a URL."
        ),
    )


def _get_client() -> anthropic.Anthropic:
    """Separate helper so tests can monkeypatch."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # Raise an api_error rather than letting the SDK raise an auth error
        # with a less clear message.
        raise ExtractError(
            status="api_error",
            message="ANTHROPIC_API_KEY is not set in the environment.",
        )
    return anthropic.Anthropic(api_key=api_key)


# ---------------------------------------------------------------------------
# Result builders
# ---------------------------------------------------------------------------


def _build_resort_result(
    tool_input: dict, source_urls: list[str], base_url: Optional[str]
) -> schemas.ExtractedResort:
    courses_in = tool_input.pop("courses", None) or []
    # Images are disabled — extraction returned too many wrong/hallucinated
    # URLs (e.g., restaurant food photos, non-image paths). The
    # `entity_images` table and UI code are preserved for future re-enablement.
    tool_input.pop("image_urls", None)
    image_urls: list[str] = []
    image_candidates: list[schemas.ImageCandidate] = []

    # Build the inner GolfResortCreate — tolerate per-course validation errors
    # by dropping the bad course with a warning instead of failing the whole
    # resort extraction.
    validated_courses: list[schemas.GolfCourseCreate] = []
    course_warnings: list[str] = []
    for i, c in enumerate(courses_in):
        if not isinstance(c, dict):
            continue
        # Drop resort_id — the backend sets it when we persist.
        clean = {k: v for k, v in c.items() if k != "resort_id"}
        try:
            validated_courses.append(schemas.GolfCourseCreate(**clean))
        except Exception as e:
            bad_name = clean.get("name", f"index {i}")
            course_warnings.append(
                f"dropped course '{bad_name}' due to validation: {str(e)[:120]}"
            )

    try:
        resort_create = schemas.GolfResortCreate(
            **tool_input,
            courses=validated_courses,
            image_urls=image_urls,
            source_urls=source_urls,
        )
    except Exception as e:
        raise ExtractError(
            status="ambiguous",
            message=f"Extraction returned an invalid resort shape: {e}",
            partial_data=tool_input,
        )

    warnings = _warnings_for(tool_input) + course_warnings
    return schemas.ExtractedResort(
        data=resort_create,
        source_urls=source_urls,
        image_candidates=image_candidates,
        partial=bool(warnings),
        warnings=warnings,
    )


def _build_course_result(
    tool_input: dict,
    source_urls: list[str],
    base_url: Optional[str],
    existing_parent_resort_lookup,
) -> schemas.ExtractedCourse:
    possible_parent_name = tool_input.pop("possible_parent_resort_name", None)
    # Images disabled — see _build_resort_result comment.
    tool_input.pop("image_urls", None)
    image_urls: list[str] = []
    image_candidates: list[schemas.ImageCandidate] = []

    try:
        course_create = schemas.GolfCourseCreate(
            **tool_input,
            image_urls=image_urls,
            source_urls=source_urls,
        )
    except Exception as e:
        raise ExtractError(
            status="ambiguous",
            message=f"Extraction returned an invalid course shape: {e}",
            partial_data=tool_input,
        )

    possible_parent = None
    if possible_parent_name:
        existing_id = None
        if existing_parent_resort_lookup is not None:
            try:
                existing = existing_parent_resort_lookup(possible_parent_name)
                if existing is not None:
                    existing_id = existing.id
            except Exception:
                existing_id = None
        possible_parent = schemas.PossibleParentResort(
            detected_name=possible_parent_name,
            existing_resort_id=existing_id,
        )

    warnings = _warnings_for(tool_input)
    return schemas.ExtractedCourse(
        data=course_create,
        source_urls=source_urls,
        image_candidates=image_candidates,
        possible_parent_resort=possible_parent,
        partial=bool(warnings),
        warnings=warnings,
    )


def _warnings_for(tool_input: dict) -> list[str]:
    """Surface common 'partial extraction' signals to the UI."""
    warnings: list[str] = []
    if not tool_input.get("country_code"):
        warnings.append("country_code missing — set it before saving")
    if not tool_input.get("description"):
        warnings.append("description missing")
    return warnings


# ---------------------------------------------------------------------------
# Image validation (FR-006b, research R4)
# ---------------------------------------------------------------------------


def _resolve_image_urls(urls: list[str], base_url: Optional[str]) -> list[str]:
    """Resolve relative / protocol-relative URLs against the page's base URL.

    Handles:
      - Absolute: https://cdn.example.com/x.jpg → unchanged
      - Protocol-relative: //cdn.example.com/x.jpg → adds scheme
      - Path-absolute: /images/hero.jpg → adds scheme + host
      - Path-relative: images/hero.jpg → adds full base
    Drops entries that aren't strings or don't look URL-ish.
    """
    from urllib.parse import urljoin

    out: list[str] = []
    for raw in urls:
        if not isinstance(raw, str) or not raw.strip():
            continue
        if base_url:
            resolved = urljoin(base_url, raw)
        else:
            resolved = raw
        # Guard against nonsense / javascript: / data: leaking through
        if not resolved.lower().startswith(("http://", "https://")):
            continue
        if resolved not in out:
            out.append(resolved)
    return out


# Browser-ish UA so CDNs don't 403 on us.
_IMAGE_VALIDATE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "image/*,*/*;q=0.8",
    "Range": "bytes=0-0",  # ranged GET: most broadly supported "is this alive?" check
}


def _validate_one_image(url: str) -> schemas.ImageCandidate:
    """Validate an image URL using a ranged GET (1-byte body) with a browser UA.

    Ranged GET works where HEAD fails — many image CDNs return 405 on HEAD or
    403 without a browser UA. We still go through the SSRF-guarded primitives.
    """
    try:
        _check_scheme(url)
        parsed = urlparse(url)
        if not parsed.hostname:
            return schemas.ImageCandidate(url=url, validation="unreachable")
        _resolve_and_check(parsed.hostname, parsed.port)
    except fetcher.FetchError:
        return schemas.ImageCandidate(url=url, validation="unreachable")

    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT_S,
        read=READ_TIMEOUT_S,
        write=READ_TIMEOUT_S,
        pool=READ_TIMEOUT_S,
    )
    try:
        with httpx.Client(
            follow_redirects=True, timeout=timeout, trust_env=False
        ) as client:
            response = client.get(url, headers=_IMAGE_VALIDATE_HEADERS)
            _verify_peer(response)
    except fetcher.FetchError:
        return schemas.ImageCandidate(url=url, validation="unreachable")
    except httpx.HTTPError:
        return schemas.ImageCandidate(url=url, validation="unreachable")

    if response.status_code not in (200, 206):
        return schemas.ImageCandidate(url=url, validation="unreachable")
    ct = (response.headers.get("content-type") or "").lower()
    # Strip query string before checking extensions (many CDNs add ?w=…&h=…).
    path_lower = url.split("?", 1)[0].lower()
    has_image_ext = path_lower.endswith(
        (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp", ".svg")
    )
    if ct.startswith("image/"):
        return schemas.ImageCandidate(url=url, validation="ok")
    if ct and not ct.startswith("image/"):
        # Definitively not an image (e.g., text/html).
        return schemas.ImageCandidate(url=url, validation="wrong_type")
    # No content-type exposed — only trust the URL if it has an image extension.
    if has_image_ext:
        return schemas.ImageCandidate(url=url, validation="unknown")
    return schemas.ImageCandidate(url=url, validation="wrong_type")


def validate_image_candidates(urls: list[str]) -> list[schemas.ImageCandidate]:
    """Parallel ranged-GET validation of image URLs (research R4)."""
    if not urls:
        return []
    with ThreadPoolExecutor(max_workers=IMAGE_VALIDATE_WORKERS) as ex:
        return list(ex.map(_validate_one_image, urls))
