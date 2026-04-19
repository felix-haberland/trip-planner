"""Unit tests for app.text_utils.normalize_name (FR-003a, research R7)."""

from app.text_utils import normalize_name


def test_lowercase_and_trim():
    assert normalize_name("  Monte Rei  ") == "monte rei"


def test_collapses_internal_whitespace():
    assert normalize_name("Monte    Rei\tGolf") == "monte rei golf"


def test_strips_punctuation():
    assert normalize_name("St. Andrews - Old Course!") == "st andrews old course"


def test_ampersand_becomes_and():
    # "Golf & Country Club" and "Golf and Country Club" should normalize identically.
    a = normalize_name("Monte Rei Golf & Country Club")
    b = normalize_name("Monte Rei Golf and Country Club")
    assert a == b == "monte rei golf and country club"


def test_diacritics_stripped():
    assert normalize_name("Nürburgring") == "nurburgring"
    assert normalize_name("São Paulo Golf") == "sao paulo golf"


def test_case_and_punctuation_variants_are_equivalent():
    assert normalize_name("St Andrews Old Course") == normalize_name(
        "ST. ANDREWS, OLD-COURSE"
    )


def test_trailing_descriptors_are_not_conflated():
    # Per R7: only exact normalized match counts; "Monte Rei Golf" is NOT the
    # same as "Monte Rei Golf & Country Club".
    a = normalize_name("Monte Rei Golf")
    b = normalize_name("Monte Rei Golf & Country Club")
    assert a != b


def test_empty_and_none():
    assert normalize_name("") == ""
    assert normalize_name(None) == ""  # type: ignore[arg-type]
