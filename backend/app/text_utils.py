"""Text normalization helpers (spec 006, FR-003a).

`normalize_name` produces the `name_norm` value used for dedup checks and
fuzzy name lookups in the golf library. See
`specs/006-golf-resorts-library/research.md` R7 for the rationale behind
each step.
"""

from __future__ import annotations

import re
import unicodedata

# Punctuation to strip: ASCII punctuation that commonly varies across sources.
# Hyphens and dashes included. Forward slash and backslash included so
# "Golf & Country Club / North Course" normalizes cleanly.
_PUNCT_RE = re.compile(r"[.,;:!?'\"/\\\-_()\[\]{}]")
_WS_RE = re.compile(r"\s+")


def normalize_name(value: str) -> str:
    """Return a normalized form of `value` for dedup and fuzzy lookup.

    Steps: NFKD-decompose → drop non-ASCII (strip diacritics) → replace
    `&` with `and` → lowercase → strip ASCII punctuation → collapse
    whitespace to single spaces → strip ends.
    """
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    ascii_only = ascii_only.replace("&", " and ")
    lower = ascii_only.lower()
    no_punct = _PUNCT_RE.sub(" ", lower)
    collapsed = _WS_RE.sub(" ", no_punct).strip()
    return collapsed
