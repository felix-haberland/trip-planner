# Feature Specification: Visit-History Filtering (3-Tier)

**Feature Branch**: `feat/005-visit-history-filtering`
**Created**: 2026-04-18
**Status**: Implemented (retroactive spec)
**Input**: Smart filtering of search results based on the couple's `visit_again` preferences, with surfacing of high-scoring filtered destinations.

## Summary

VacationMap's `region_visits` table records the couple's visits to regions, including a `visit_again` preference: `never`, `not_soon`, `few_years`, or `anytime`. The original 001 spec only mentioned filtering `never`. In practice, this was too coarse:

- `never` should hard-filter (correct).
- `not_soon` should hard-filter from results, but **high-scoring** filtered destinations should be surfaced to the AI so it can mention them ("Algarve would also fit but is excluded due to a recent visit").
- `few_years` should remain in results but with an annotation, only suggested for exceptional fits.
- `anytime` (or no record) should appear normally.

The AI also needs the full visit list with annotations in the system prompt to reason about geographic and timing patterns ("you visited Thailand recently, so I'm avoiding nearby SE Asia").

## User Scenarios & Testing

### User Story 1 - Recently visited destinations don't get re-suggested but are surfaced (Priority: P1)

The user visited Algarve six months ago and rated it 9/10 with `visit_again: not_soon`. They start a new golf trip in June. The AI does not suggest Algarve, but it tells them: "Algarve would have scored 8.2 — excluded because you visited recently."

**Why this priority**: Without surfacing, the user might assume the AI didn't consider Algarve (lack of trust). With surfacing, the AI demonstrates it knows the data and respects the constraint.

**Independent Test**: Mark a high-scoring region as `not_soon` in `vacation.db`. Trigger a search. Verify it's absent from the AI's suggestions but mentioned as filtered.

**Acceptance Scenarios**:

1. **Given** a region has `visit_again = not_soon` and a high score for the requested month, **When** `search_destinations` runs, **Then** the region is absent from `results` but present in `excluded_due_to_recent_visit` (top 5).
2. **Given** the search returns `excluded_due_to_recent_visit`, **When** the AI composes its message, **Then** it MUST mention these to the user (per `instructions.md`).
3. **Given** a region has `visit_again = never`, **When** `search_destinations` runs, **Then** the region is absent from both `results` AND `excluded_due_to_recent_visit`. It is hard-hidden.

---

### User Story 2 - "Few years" destinations stay visible but flagged (Priority: P2)

The user visited Tuscany 18 months ago and marked it `visit_again: few_years`. It scored 9/10 for an autumn culture trip. The AI sees it in results with an annotation, decides it's still an exceptional fit, and suggests it with a `pre_filled_exclude_reason` like "Visited recently — revisit in a few years" so the user can dismiss with one click if they don't want to revisit.

**Why this priority**: Some destinations are worth a return visit despite recent timing. Hiding them is too aggressive; suggesting them blindly ignores the user's preference. The annotation lets the AI exercise judgment.

**Independent Test**: Mark a region as `few_years`. Trigger a relevant search. Verify the region appears in results with `visit_again` populated and that the AI uses `pre_filled_exclude_reason` if it suggests it.

**Acceptance Scenarios**:

1. **Given** a region has `visit_again = few_years`, **When** `search_destinations` runs, **Then** the region appears in `results` with a `visit_again` annotation containing the rating and rating_summary.
2. **Given** the AI sees a `few_years` annotation and judges the destination an exceptional fit, **When** it calls `suggest_for_review`, **Then** it MUST set `pre_filled_exclude_reason` to a string like "Visited recently — revisit in a few years".
3. **Given** the suggestion has `pre_filled_exclude_reason`, **When** the user clicks Exclude in the UI, **Then** the prompt is pre-populated with that reason.

---

### User Story 3 - AI can reason about geographic/timing patterns (Priority: P2)

The user visited Thailand 6 months ago. They ask for a beach trip. The AI should consider not just Thailand specifically but nearby SE Asia (Vietnam, Malaysia) — applying the same recency logic to similar destinations even if the data doesn't formally exclude them.

**Why this priority**: Pattern reasoning makes the AI feel intelligent rather than mechanical. It mirrors how a human travel agent would think.

**Independent Test**: With recent visits in a region, ask for trip suggestions in a similar geography. Observe whether the AI surfaces this consideration in its reasoning.

**Acceptance Scenarios**:

1. **Given** the system prompt includes the full visit history with timing, **When** the AI suggests destinations, **Then** its `ai_reasoning` should reference visit-history patterns when relevant (e.g., "avoiding SE Asia given recent Thailand trip").
2. **Given** an excluded destination's reason mentions geography (e.g., "too close to Tenerife"), **When** the AI suggests new destinations, **Then** it should consider the excluded reason as a signal about similar geographies (per `instructions.md`'s "Advanced Exclusion Reasoning" section).

---

### Edge Cases

- A region has no `region_visits` entry — treat as `anytime` (include normally).
- The user re-rates a recent visit from `not_soon` to `anytime`. Next search includes it normally.
- Multiple visits to the same region — the most recent visit's `visit_again` wins (current implementation queries the latest by year/month).
- All matching destinations for a search are filtered out by `never` / `not_soon`. The AI should inform the user and suggest broadening criteria.

## Requirements

### Functional Requirements

- **FR-001**: `search_destinations` MUST partition `region_visits` rows by `visit_again` into three buckets: hard-exclude (`never` + `not_soon`), include-with-annotation (`few_years`), and include-normally (`anytime` or no record).
- **FR-002**: When `exclude_visited_never=true` (default), the system MUST hard-exclude `never` and `not_soon` regions from `results`.
- **FR-003**: For `not_soon` regions only (NOT `never`), the system MUST also return them in `excluded_due_to_recent_visit` (top 5 by score) so the AI can mention them.
- **FR-004**: For `few_years` regions, the system MUST include them in `results` with a `visit_again` annotation containing `visit_again`, `rating`, `rating_summary`.
- **FR-005**: The system prompt MUST include the full visit history with country code, region name, rating, `visit_again`, and rating summary.
- **FR-006**: The system prompt MUST include a note explaining the 3-tier filtering semantics so the AI understands the data shape.
- **FR-007**: `instructions.md` MUST instruct the AI to (a) mention `excluded_due_to_recent_visit` destinations to the user, (b) only suggest `few_years` if exceptional with a `pre_filled_exclude_reason`, and (c) reason about geographic/timing patterns from visit history.

### Key Entities

- **VisitRecord** (in VacationMap's `region_visits`): `region_id`, `visit_again` (`never`|`not_soon`|`few_years`|`anytime`), `rating`, `rating_summary`, `visited_month`, `visited_year`, `summary`.
- **excluded_due_to_recent_visit**: A search-result-side bucket of high-scoring `not_soon` destinations, included in the tool result so the AI can surface them transparently.

## Success Criteria

- **SC-001**: 0% of `never`-marked destinations appear in any tool result.
- **SC-002**: 100% of `not_soon`-marked destinations are absent from `results` but visible in `excluded_due_to_recent_visit` if their score qualifies for the top 5.
- **SC-003**: ≥80% of `not_soon` filtered destinations are mentioned by the AI in its reply (measured by inspecting message content for region names from `excluded_due_to_recent_visit`).
- **SC-004**: When the AI suggests a `few_years` destination, ≥90% of suggestions include a `pre_filled_exclude_reason`.

## Assumptions

- VacationMap's `visit_again` values are well-maintained — users update them as their preferences shift.
- The user accepts that "exceptional fit" for `few_years` is the AI's judgment, not a hard rule.
- Geographic pattern reasoning is best-effort (the AI's general knowledge), not data-driven (we don't store country adjacency).

## Constitution Check

- **Principle I (Data Safety)**: ✅ All visit access is SELECT-only on `vacation.db`.
- **Principle II (Transparent AI)**: ✅ The 3-tier semantics are explained in both the system prompt and `instructions.md`.
- **Principle V (Simple by Default)**: ✅ Three buckets, no new tables, no new dependencies.
- All other principles unaffected.
