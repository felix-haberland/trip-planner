# Feature Specification: Region Linking & Fuzzy Matching

**Feature Branch**: `feat/004-region-linking-and-fuzzy-matching`
**Created**: 2026-04-18
**Status**: Implemented (retroactive spec)
**Input**: Resolve vague AI destination names to specific VacationMap regions automatically, with manual override.

## Summary

Claude often suggests destinations using vague names like "Ireland", "Costa del Sol, Spain", or "Portugal Golf Coast". VacationMap stores specific regions (e.g., "Western Ireland", "Scotland Lowlands"). Without resolution, these suggestions appear as unscored placeholders, robbing the user of real data.

This feature introduces:

1. **Automatic fuzzy resolution** in `suggest_for_review` — a 6-step fallback chain that maps a vague name to the best matching `country_code:region_name` lookup key.
2. **Transparency** — when fuzzy matching changes the destination, the tool result tells Claude which specific region was matched, plus the other regions in that country, so Claude can explain to the user.
3. **Manual override** — frontend autocomplete to search regions and re-link a suggested or shortlisted destination if automatic resolution was wrong.
4. **Real-score backfill** — when a region is linked (auto or manual), the scores are immediately resolved from `vacation.db` for the trip's `target_month` and stored as `scores_snapshot`.

## User Scenarios & Testing

### User Story 1 - Vague AI suggestions get real scores (Priority: P1)

The user asks for golf destinations. Claude suggests "Ireland" without specifying a region. The system resolves it to "Western Ireland" (best `golf_score` in IE), looks up real June scores, and presents the suggestion with full data — not as an unscored placeholder.

**Why this priority**: Score-backed suggestions are 6× more useful than unscored ones. This was a major source of friction.

**Independent Test**: In a test trip, send "suggest some Irish golf destinations". Verify the resulting suggestions have populated `scores_snapshot`, the displayed region name is specific (not just "Ireland"), and the AI's response message explains the match.

**Acceptance Scenarios**:

1. **Given** Claude calls `suggest_for_review` with `destination_name="Ireland"` and no `region_lookup_key`, **When** the resolver runs, **Then** it returns a key like `IE:Western Ireland` (the IE region with highest `golf_score`).
2. **Given** the destination was fuzzy-matched, **When** the tool result is returned, **Then** it includes `fuzzy_matched: true`, `matched_region: "Western Ireland"`, `other_regions_in_country: [...]`, and a `note` instructing the AI to update its reasoning.
3. **Given** the destination is resolved to a VacationMap key, **When** the suggestion is persisted, **Then** `scores_snapshot` contains real DB scores for the trip's `target_month`.

---

### User Story 2 - Manual region linking when automatic resolution is wrong (Priority: P2)

The AI suggests "Costa del Sol, Spain" and the resolver picks `ES:Costa del Sol`. The user actually wanted `ES:Costa Blanca`. The user clicks Link Region on the suggestion, types "Costa Blanca" into the autocomplete, and selects the correct region. Real scores update.

**Why this priority**: Fuzzy matching is correct ~90% of the time but the long tail matters. Without manual override, users would have to delete and re-create suggestions.

**Independent Test**: Take an unscored or wrongly-matched suggestion. Click Link Region. Type a partial region name. Verify autocomplete returns matching regions. Select one and verify scores populate.

**Acceptance Scenarios**:

1. **Given** any suggested or shortlisted destination, **When** the user clicks Link Region and types ≥2 characters, **Then** matching regions appear in the autocomplete (max 20).
2. **Given** the user selects a region, **When** the link is confirmed, **Then** the destination's `region_lookup_key` is updated and `scores_snapshot` is rebuilt from `vacation.db` for the trip's `target_month`.
3. **Given** the link succeeds, **When** the trip detail re-renders, **Then** the destination shows the new region name and real scores.

---

### User Story 3 - Region disambiguation across countries (Priority: P2)

Claude suggests "Ireland". Without smart resolution, a fuzzy LIKE match could pick "Northern Ireland" (in GB), which is wrong. The resolver runs the country-name match BEFORE fuzzy region match to avoid this.

**Why this priority**: Cross-country name collisions ("Georgia" the country vs "Georgia" the US state if added later) are subtle bugs that erode trust.

**Independent Test**: Suggest "Ireland". Verify the resolved key starts with `IE:`, not `GB:`.

**Acceptance Scenarios**:

1. **Given** a destination name is also a country name (e.g., "Ireland", "Scotland"), **When** the resolver runs, **Then** step 2 (country-name → best region) wins before step 5 (fuzzy LIKE on region name).
2. **Given** a multi-word name like "Portugal Golf Coast", **When** no exact or simple match works, **Then** step 6 (try each word as a country) finds "Portugal" and picks its best region.

---

### Edge Cases

- The destination is genuinely not in VacationMap (e.g., "Costa Navarino, Greece" if Greece isn't covered). Resolver returns `None`. Suggestion is persisted with `region_lookup_key = NULL` and `scores_snapshot = NULL`. UI shows "unscored" badge.
- The user links a destination that's already linked. The link endpoint overwrites the existing key and re-resolves scores.
- The user types fewer than 2 characters in the search. Backend returns an empty array (no expensive query).
- Two regions in the same country tie on `golf_score`. The resolver picks the first SQL result — non-deterministic but acceptable for a tiebreaker.

## Requirements

### Functional Requirements

- **FR-001**: When `suggest_for_review` is called without `region_lookup_key`, the system MUST attempt fuzzy resolution from `destination_name`.
- **FR-002**: The resolver MUST follow the documented 6-step fallback chain (exact → country-name → country+region → country-name best → fuzzy LIKE → multi-word splitting).
- **FR-003**: Step 2 (country-name match) MUST run before step 5 (fuzzy LIKE) to prevent cross-country name collisions.
- **FR-004**: When fuzzy resolution changes the destination, the tool result MUST include `fuzzy_matched: true`, `matched_region`, and `other_regions_in_country` (top 5 by `golf_score`).
- **FR-005**: When a region is resolved (auto or manual), the system MUST immediately look up real scores from `vacation.db` for the trip's `target_month` and store them as `scores_snapshot`.
- **FR-006**: System MUST expose `GET /api/vacationmap/regions/search?q=` returning `[{ lookup_key, label }]` for autocomplete (max 20 results, requires q.length ≥ 2).
- **FR-007**: System MUST expose `GET /api/vacationmap/regions/{lookup_key}/details?month=` returning full region data for a destination-detail popup.
- **FR-008**: System MUST expose `POST /api/trips/{trip_id}/{section}/{dest_id}/link` (where section is `suggested` or `shortlisted`) to update a destination's `region_lookup_key` and re-resolve scores.
- **FR-009**: All region lookups MUST use raw SELECT SQL — no writes to `vacation.db`.
- **FR-010**: When a destination has no matching VacationMap region (after all fallbacks), the system MUST persist it with `region_lookup_key = NULL` and `scores_snapshot = NULL`. The UI MUST display "unscored" rather than fabricating scores.

### Key Entities

- **region_lookup_key**: A string `country_code:region_name` (e.g., `PT:Algarve`). Stable across VacationMap re-imports.
- **scores_snapshot**: JSON blob with `total_score`, `weather_score`, `cost_relative`, `busyness_relative`, `attractiveness`, `golf_score`, `flight_hours`. Populated only when a region is linked.

## Success Criteria

- **SC-001**: ≥80% of AI-suggested destinations resolve to real VacationMap regions automatically (measured by % of suggestions with non-NULL `region_lookup_key`).
- **SC-002**: 100% of resolved destinations have `scores_snapshot` populated within the same request.
- **SC-003**: Manual re-linking takes ≤3 clicks (Link Region button, type, select).
- **SC-004**: 0% of fuzzy resolutions match "Ireland" to "Northern Ireland" (the canonical disambiguation test).

## Assumptions

- VacationMap region names are stable enough that exact-match works for most explicit AI suggestions.
- The user can recognize when fuzzy matching went wrong (the AI's reply mentions the matched region; the destination name in the UI shows it).
- Score snapshots can become stale if VacationMap data changes — this is acceptable; users can manually re-link to refresh.

## Constitution Check

- **Principle IV (Stable Identifiers)**: ✅ All cross-DB references use `country_code:region_name`.
- **Principle V (Simple by Default)**: ⚠ The 6-step resolver is non-trivial. Justified because it dramatically improves AI usefulness — alternative would be retraining Claude to always know specific region names, which is unreliable.
- **Data Safety (Principle I)**: ✅ All `vacation.db` access is SELECT-only.
- **Principle II (Transparent AI)**: ✅ Resolver behavior is documented in `instructions.md` so the AI can describe it to the user.
