# Research: Golf Courses & Resorts Library (spec 006)

Phase 0 output. Resolves the unknowns flagged in `plan.md` Technical Context and the few items the spec deferred to planning.

## R1 — Anthropic SDK: name-only extraction via server-side web search

**Question**: How does the backend invoke Claude with web search enabled for name-only extraction (FR-006)?

**Decision**: Use the Anthropic Messages API's server-side **web search tool** (`web_search_20250305`) as part of the `tools` list when the user submits a name without a URL. Claude performs the search, visits the top candidate pages, and returns a structured JSON response via a tool-use round-trip. The backend runs a bounded tool-use loop (same pattern as `chat.py`) until Claude emits the final `extracted_data` JSON.

**Implementation sketch**:

```python
# backend/app/extraction.py (conceptual)
tools = [
    {"type": "web_search_20250305", "name": "web_search", "max_uses": 5},
    EXTRACT_RESORT_TOOL | EXTRACT_COURSE_TOOL,  # our client-side structured-return tool
]
```

The client-side structured-return tool is a regular tool definition whose input schema mirrors the JSON shape we want. When Claude emits a `tool_use` block for it, we treat the input as the extraction result. This pattern keeps the SDK call simple (no streaming, no manual function-calling protocol) and separates "gather" from "return".

**Rationale**: Anthropic's server-side web search runs search + page fetch inside Claude's own environment, avoiding the need for us to stand up our own search integration. The assumption in the spec ("Claude's web search tool is available") is validated by current (2026-Q1) SDK support.

**Alternatives considered**:

- **Hit a third-party search API ourselves** (SerpAPI, Bing, Brave Search) and feed URLs to Claude. Rejected: more moving parts, another API key to manage, more latency.
- **Google Custom Search**: same objection, plus stricter terms-of-service.
- **No web search — require URLs**: would force users into URL-only input, violating FR-006. Reserved as a fallback only if the SDK drops the tool.

**Risks**:

- If Anthropic changes the web search tool schema, `extraction.py` needs an update. Mitigation: keep the tool-handling logic narrowly scoped in one file.
- Cost: web search calls cost more than plain completions. Mitigation: seed script throttling (FR-S-004); UI flow intentionally unguarded per spec clarification (user accepts the responsibility).

## R2 — SSRF guardrails on server-side URL fetch (FR-005a)

**Question**: How do we enforce FR-005a's scheme allowlist + post-DNS private-IP blocking + 10 s timeout + 5 MB cap + redirect re-validation using `httpx`?

**Decision**: Implement `fetcher.safe_get(url: str) -> FetchResult` in a new `backend/app/fetcher.py` with the following pattern:

1. **Scheme**: parse with `urllib.parse.urlparse`; reject unless `scheme in ("http", "https")`.
2. **Host resolution**: for each candidate URL (initial + every redirect), call `socket.getaddrinfo(host, None)`. Reject if any resolved address falls inside the reserved ranges using `ipaddress.ip_address()` checks: `is_private`, `is_loopback`, `is_link_local`, `is_reserved`, `is_multicast`, plus an explicit check for `0.0.0.0` / `::`.
3. **Pin the resolved IP**: once a safe IP is chosen, pass it as `transport=httpx.HTTPTransport(local_address=None)` with a custom connection that uses the already-resolved IP (avoids TOCTOU where DNS would re-resolve to a private IP between check and connect). Pattern: use `httpx.HTTPTransport` with a `socket`-level adapter, or simpler: pass `server_hostname` for SNI and connect by IP string. Simplest is to re-check after connect: `response.extensions["network_stream"].get_extra_info("peername")` and verify the peer address.
4. **Timeout**: `httpx.Timeout(connect=3.0, read=7.0, total=10.0)`.
5. **Size cap**: stream the body (`client.stream("GET", ...)`) and accumulate bytes; abort and return truncated/flagged when `len >= 5 * 1024 * 1024`.
6. **Redirects**: `follow_redirects=False`. Handle the redirect chain manually by re-running step 1–3 for each `Location` header; hard-limit to 5 redirects.

**Rationale**: httpx is already a transitive dependency of the Anthropic SDK, so no new top-level dependency is incurred. Manual redirect handling is clunky but is the only way to re-validate the resolved host on every hop — without it, a 302 to `http://127.0.0.1:9000` would bypass the initial check.

**Alternatives considered**:

- **`requests` library**: same limitation (doesn't expose post-DNS IP reliably), and would add a dependency. Rejected.
- **Use a proxy service (e.g., a URL fetcher SaaS)**: adds cost, adds a network hop, and changes the trust boundary for no real gain in a local-app context.
- **Skip IP-level checks (scheme + timeout only)**: violates the FR-005a decision. Rejected.

**Testing**: `test_fetcher.py` covers: wrong scheme, private IPv4, private IPv6, loopback, link-local, timeout, oversized body, redirect to private IP, 5+ redirect chain. Use pytest `monkeypatch` on `socket.getaddrinfo` to simulate private-IP resolutions.

## R3 — Fuzzy `name_query` implementation for library search

**Question**: FR-015 / FR-015a add an optional `name_query` parameter. How is "fuzzy" implemented against SQLite?

**Decision**: Two-tier matching in `crud.search_resorts()` / `crud.search_courses()`:

1. **Normalize the query**: apply the same `name_norm` transform (lowercase, collapse whitespace, strip punctuation).
2. **Tier 1 — prefix / contains on `name_norm`**: `SELECT ... WHERE name_norm LIKE :pattern` with `:pattern = f"%{query_norm}%"`. Order by `LENGTH(name_norm)` ascending so shorter matches rank higher (a 3-word resort name that matches "monte rei" outranks a 6-word resort name).
3. **Tier 2 — token overlap**: if Tier 1 yields < 3 results, split `query_norm` on whitespace and search for any token in `name_norm` via a UNION of LIKE patterns. Score each hit by the number of token matches; return top N.

No external fuzzy library. SQLite `LIKE` plus the existing `name_norm` index gets us 95% of the ergonomic value of fuzzy matching for names that users actually type. If we ever need edit-distance matching, we can add Python-side scoring post-SQL filter, but not in v1.

**Rationale**: Keeps the simple-by-default constitution principle. Honours the `name_norm` index created in FR-003a. No new dependency.

**Alternatives considered**:

- **SQLite FTS5 virtual table**: overkill for the dataset size (≤ ~1500 entities) and adds migration complexity (FTS tables can't be `ALTER`'d). Rejected.
- **Python `difflib` or `rapidfuzz` post-filter**: rapidfuzz would add a compiled dependency; difflib is pure Python but O(N) on every call. Not needed for v1.
- **Store n-grams**: premature optimization.

## R4 — Image URL HEAD validation (FR-006b)

**Question**: FR-006b says "lightweight HEAD validation" on image URLs — synchronous or async?

**Decision**: **Synchronous within the same extraction round-trip, best-effort and non-blocking**. When the AI returns up to 5 image URLs, the backend runs a `httpx.AsyncClient` with `asyncio.gather()` across all of them doing HEAD requests with a 3 s timeout each. Each image gets a `validation` tag: `ok` (2xx + image content-type), `unreachable` (non-2xx / timeout), `wrong_type` (not `image/*`), or `unknown` (HEAD not allowed — some CDNs). The frontend renders all images but badges non-`ok` ones so the user can see and decide. No image is filtered out server-side.

**Rationale**: The user saves the extraction anyway (per FR-006b — "still saved if the user chooses to keep them"), so we're validating for display, not gating. Running HEADs in parallel adds at most 3 s to the 20 s extraction budget, well within SC-001's 10-minutes-for-5-entries envelope. Goes through the same `fetcher.safe_get` SSRF gate.

**Alternatives considered**:

- **Skip validation entirely**: leaves users staring at broken image icons. Rejected.
- **Async validation after save, updating DB on completion**: more complex for little gain; first-page-load of the library would still show broken images until the background job completes.
- **Download + cache the image locally**: explicitly out of scope per clarification round 2 ("external URLs only — no local download in v1").

## R5 — Seed data format and sourcing

**Question**: FR-S-006 calls for a readable seed file. What format, what content?

**Decision**: **YAML** at `backend/app/seed_data/golf_library_seed.yaml` with the following schema:

```yaml
version: 1
resorts:
  - name: "Monte Rei Golf & Country Club"
    country_code: PT
    url: "https://www.monte-rei.com"           # optional — drives URL extraction if present
  - name: "Son Gual"
    country_code: ES
    # no url → seed script uses name-only extraction
  # ...~100 entries total
courses:
  - name: "Old Course, St Andrews"
    country_code: GB
    url: "https://www.standrews.com/play/courses/old-course"
  # ...~20 entries total
```

The script reads the YAML, iterates entries, and for each one invokes `extraction.extract(entity_type, url=..., name=...)` followed by `crud.create_with_dedup(...)`. The YAML lives in the repo and is user-editable per FR-S-006.

**Content sourcing**: the initial resort list is compiled by Claude ahead of time during implementation, anchored on the Today's Golfer "100 best golf resorts in Continental Europe" list (https://www.todays-golfer.com/courses/best/golf-resorts-in-continental-europe/), cross-referenced with Top 100 Golf Courses Europe rankings and the spec's clarified iconic-courses shortlist (Old Course St Andrews, Royal County Down, Portmarnock, Muirfield). The shortlist is reviewed by the user before the script runs — both because it lives in YAML and because the user invokes the script explicitly.

**Rationale**: YAML is human-editable, preserves insertion order, allows comments. Python parses via PyYAML (already a transitive dep via FastAPI/uvicorn? — verify; if not, add explicitly). The schema is minimal and deliberately permissive: only `name` and `country_code` are mandatory; `url` is optional (drives URL vs name-only path).

**Alternatives considered**:

- **CSV**: easier to import into spreadsheets but messy for optional fields.
- **JSON**: no comments, less ergonomic for manual curation.
- **Hard-coded Python list**: violates FR-S-006 (must be readable/editable as data).

## R6 — Handling of `Trip.activity_weights` for existing trips

**Question**: How do we backfill existing trips in `trips.db` after adding the new column?

**Decision**: On `ALTER TABLE trips ADD COLUMN activity_weights TEXT DEFAULT '{}'`, existing rows get `'{}'` (empty dict). Per FR-017a, an empty dict triggers the free-text-inference fallback in the system prompt, so existing trips behave identically to today. No inference of weights from existing trip descriptions — that would be presumptuous and could surprise the user.

**Rationale**: Zero-migration-effort backward compatibility. Aligns with "User Owns Decisions" — the user fills in weights when they want the structured behavior.

## R7 — Dedup normalization edge cases

**Question**: FR-003a specifies the `name_norm` transform. A few ambiguous cases:

- Unicode (e.g., `"Lindner Congress & Motorsport Hotel Nürburgring"` — the `ü`): do we strip diacritics?
- Ampersands and conjunctions (`"Golf & Country Club"` vs `"Golf and Country Club"`): treat equivalently?
- Trailing descriptors (`"Monte Rei Golf"` vs `"Monte Rei Golf & Country Club"`): considered duplicate?

**Decision**:

- **Diacritics**: yes, strip. Use `unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()`. Reason: the same resort might be written with or without diacritics across sources.
- **`&` ↔ `and`**: replace `&` with `and` before punctuation stripping. Reason: the conjunction ambiguity is genuinely common in golf resort naming.
- **Trailing descriptors**: **not** considered duplicates. Only exact `name_norm` match + `country_code` + `entity_type` triggers the dedup warning. "Monte Rei Golf" and "Monte Rei Golf & Country Club" are semantically close but the user may legitimately want both if, say, one is a public pro shop and the other is the resort proper. Keep dedup tight; let the user handle near-matches via Edit/Link.

**Rationale**: Over-aggressive normalization (stripping words like "Golf", "Club") would false-positive too often. The current spec's intent is to catch typos and punctuation variants, not semantic equivalence.

## R8 — Empty library behavior for chatbot tools

**Question** (deferred from round 3 clarification as low-impact): What does `search_golf_resorts` / `search_golf_courses` return when the library is empty or no results match?

**Decision**: Return `{"results": [], "library_size": <count>}`. The non-zero `library_size` signal lets Claude distinguish "library is empty" from "library is populated but filters match nothing", and adjust its reply accordingly:

- `library_size == 0` → "Your golf library is empty. I can suggest destinations from general knowledge, or you can add resorts via the Library → Add page."
- `library_size > 0 and results == []` → "No matches in your library for these filters. Here are regional suggestions instead …"

Added to `instructions.md` as part of the library-integration ruleset (FR-017).

## R9 — Required fields on save (deferred from clarification round 3)

**Question**: Minimum fields for a valid resort/course save?

**Decision**: `name` + `country_code` required for both entity types. Everything else optional. Server-side validation via Pydantic; client-side preview highlights missing recommended fields (price_category, best_months, etc.) but allows save.

**Rationale**: Matches Option B from the clarification I was about to ask. Keeps entries searchable by country (essential for the chatbot and the filter UI) without forcing speculation on fields that are often legitimately unknown.

## R10 — Browse page full-text search (deferred from clarification round 3)

**Question**: Do we need a search box on the library browse pages in addition to the filter chips?

**Decision**: Yes — a single search input in the filter sidebar that hits `name_norm` and `description` (LIKE substring). Debounced 200 ms client-side. Implementation reuses the same normalization as FR-003a. No separate FTS table (consistent with R3).

**Rationale**: With 120+ seeded entries, filters alone are insufficient — users know resort names before they know countries. Cost is ~20 lines on the frontend and one extra filter clause on the list endpoint.

## R11 — Images in chatbot tool output (deferred from clarification round 3)

**Question**: Does `search_golf_resorts` / `search_golf_courses` return image URLs?

**Decision**: Yes — each result includes `hero_image_url` (the first `entity_images` row by `display_order`) if available. The frontend `app.js` renders this as a small thumbnail next to chatbot-suggested entities in the message stream. If no image exists, the frontend falls back to the existing generic icon. Cost: one additional JOIN in the tool's SQL; no schema change.

**Rationale**: With images seeded in, the visual signal in chatbot responses is a significant UX win for near-zero extra work. Not a spec change — the tool output format is a plan-level detail.

---

All NEEDS CLARIFICATION items resolved. Ready for Phase 1.
