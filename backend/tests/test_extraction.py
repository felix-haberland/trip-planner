"""Tests for the AI extraction pipeline (FR-005/006/008).

Mocks the Anthropic client to avoid real API calls. Verifies that each
failure mode maps to the correct ExtractError sub-status and that a
successful tool_use response flows through to an ExtractedResort/Course.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.golf import extraction


class _ToolUseBlock:
    """Mimics an Anthropic tool_use content block."""

    type = "tool_use"

    def __init__(self, name: str, input_: dict):
        self.name = name
        self.input = input_


class _TextBlock:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _FakeResponse:
    def __init__(self, content, stop_reason="tool_use"):
        self.content = content
        self.stop_reason = stop_reason


# --- Happy paths -----------------------------------------------------


def test_resort_name_only_success(monkeypatch):
    """Name-only extraction: Claude invokes web_search server tool, then
    emits extracted_resort. The client sees a single API response."""
    tool_input = {
        "name": "Son Gual Mallorca",
        "country_code": "ES",
        "hotel_type": "luxury",
        "price_category": "\u20ac\u20ac\u20ac\u20ac",
        "best_months": [4, 5, 6, 9, 10],
        "description": "A modern parkland course in Mallorca.",
        "rank_rating": 85,
    }
    fake_response = _FakeResponse(
        content=[
            _TextBlock("I'll search for this resort…"),
            _ToolUseBlock("extracted_resort", tool_input),
        ]
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch.object(extraction, "_get_client", return_value=fake_client):
        with patch.object(extraction, "validate_image_candidates", return_value=[]):
            result = extraction.extract_resort(name="Son Gual Mallorca")

    assert result.entity_type == "resort"
    assert result.data.name == "Son Gual Mallorca"
    assert result.data.country_code == "ES"


def test_resort_url_success(monkeypatch):
    """URL-based extraction: fetcher returns page body, Claude extracts."""
    fake_page = b"<html><title>Monte Rei</title><body>...</body></html>"
    fake_fetched = MagicMock(
        body_bytes=fake_page, status_code=200, final_url="https://monte-rei.com"
    )

    tool_input = {
        "name": "Monte Rei Golf & Country Club",
        "country_code": "PT",
        "hotel_type": "luxury",
    }
    fake_response = _FakeResponse(
        content=[_ToolUseBlock("extracted_resort", tool_input)]
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch.object(extraction, "_get_client", return_value=fake_client):
        with patch.object(extraction.fetcher, "safe_get", return_value=fake_fetched):
            with patch.object(extraction, "validate_image_candidates", return_value=[]):
                result = extraction.extract_resort(url="https://monte-rei.com")
    assert result.data.name == "Monte Rei Golf & Country Club"
    assert "https://monte-rei.com" in result.source_urls


def test_course_returns_possible_parent_hint(monkeypatch):
    tool_input = {
        "name": "North Course",
        "country_code": "PT",
        "holes": 18,
        "par": 72,
        "type": "parkland",
        "possible_parent_resort_name": "Monte Rei Golf & Country Club",
    }
    fake_response = _FakeResponse(
        content=[_ToolUseBlock("extracted_course", tool_input)]
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    fake_existing = MagicMock(id=42)
    fake_lookup = MagicMock(return_value=fake_existing)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch.object(extraction, "_get_client", return_value=fake_client):
        with patch.object(extraction, "validate_image_candidates", return_value=[]):
            result = extraction.extract_course(
                name="Monte Rei North",
                existing_parent_resort_lookup=fake_lookup,
            )

    assert result.possible_parent_resort is not None
    assert (
        result.possible_parent_resort.detected_name == "Monte Rei Golf & Country Club"
    )
    assert result.possible_parent_resort.existing_resort_id == 42


# --- Error paths: one per status ------------------------------------


def test_api_timeout_raises_api_error(monkeypatch):
    import anthropic

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = anthropic.APITimeoutError(
        request=MagicMock()
    )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch.object(extraction, "_get_client", return_value=fake_client):
        with pytest.raises(extraction.ExtractError) as exc:
            extraction.extract_resort(name="Some Resort")
    assert exc.value.status == "api_error"
    assert "timed out" in exc.value.message.lower()


def test_rate_limit_raises_api_error(monkeypatch):
    import anthropic

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = anthropic.RateLimitError(
        "rate limited",
        response=MagicMock(status_code=429),
        body=None,
    )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch.object(extraction, "_get_client", return_value=fake_client):
        with pytest.raises(extraction.ExtractError) as exc:
            extraction.extract_resort(name="Some Resort")
    assert exc.value.status == "api_error"


def test_fetch_error_bubbles_as_fetch_error(monkeypatch):
    from app.golf import fetcher

    with patch.object(
        extraction.fetcher,
        "safe_get",
        side_effect=fetcher.FetchError("blocked: loopback"),
    ):
        with pytest.raises(extraction.ExtractError) as exc:
            extraction.extract_resort(url="http://127.0.0.1/")
    assert exc.value.status == "fetch_error"
    assert "loopback" in exc.value.message


def test_name_only_no_match_when_no_return_tool(monkeypatch):
    """Name-only run that doesn't emit extracted_resort → no_match."""
    fake_response = _FakeResponse(
        content=[_TextBlock("I couldn't find a specific resort by that name.")],
        stop_reason="end_turn",
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch.object(extraction, "_get_client", return_value=fake_client):
        with pytest.raises(extraction.ExtractError) as exc:
            extraction.extract_resort(name="Nonexistent Golf Hideaway")
    assert exc.value.status == "no_match"


def test_url_no_return_tool_is_ambiguous(monkeypatch):
    """URL-based run that doesn't emit the return tool → ambiguous."""
    fake_fetched = MagicMock(
        body_bytes=b"<html>...</html>", status_code=200, final_url="https://x.com"
    )
    fake_response = _FakeResponse(
        content=[_TextBlock("Multiple resorts on this page; cannot pick one.")],
        stop_reason="end_turn",
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch.object(extraction.fetcher, "safe_get", return_value=fake_fetched):
        with patch.object(extraction, "_get_client", return_value=fake_client):
            with pytest.raises(extraction.ExtractError) as exc:
                extraction.extract_resort(url="https://listicle.example.com/top10")
    assert exc.value.status == "ambiguous"


def test_missing_api_key_is_api_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(extraction.ExtractError) as exc:
        extraction.extract_resort(name="Anything")
    assert exc.value.status == "api_error"
    assert "ANTHROPIC_API_KEY" in exc.value.message


def test_neither_url_nor_name_raises_no_match(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with pytest.raises(extraction.ExtractError) as exc:
        extraction.extract_resort()
    assert exc.value.status == "no_match"
