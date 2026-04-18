# Feature Specification: Suggest-for-Review Flow

**Feature Branch**: `feat/002-suggest-for-review-flow`
**Created**: 2026-04-18
**Status**: Implemented (retroactive spec)
**Input**: Replace direct AI shortlisting/excluding with a user-triaged review queue.

## Summary

The original 001 design had Claude directly call `shortlist_destination` and `exclude_destination`, mutating the trip's working state from the AI side. In practice this removed user agency — the AI would shortlist destinations the user hadn't seen, and exclude based on guesses. This feature replaces both tools with a single `suggest_for_review` tool that queues destinations into a "Pending Review" list for the user to triage explicitly.

This change is now codified as **constitution principle III**: "The User Owns the Decisions."

## User Scenarios & Testing

### User Story 1 - Triage AI suggestions explicitly (Priority: P1)

The user starts a trip and chats with the AI. After the AI suggests destinations, those destinations appear in a "Pending Review" panel in the UI, each with a Shortlist button, an Exclude button, and a Link Region button. The user clicks through them at their own pace. Nothing reaches the shortlist or excluded list without their action.

**Why this priority**: This is the core trust contract of the app. If the AI mutates state silently, the user can't audit or undo decisions easily.

**Independent Test**: Send a chat message asking for golf destinations. Verify destinations appear in "Pending Review" rather than directly in "Shortlisted" or "Excluded".

**Acceptance Scenarios**:

1. **Given** an active trip, **When** the user sends "suggest some golf destinations", **Then** the AI calls `suggest_for_review` for each candidate and the destinations appear in the Pending Review panel — not in Shortlisted or Excluded.
2. **Given** a destination is in Pending Review, **When** the user clicks Shortlist with an optional note, **Then** it moves to Shortlisted with the note attached.
3. **Given** a destination is in Pending Review, **When** the user clicks Exclude with a reason, **Then** it moves to Excluded with that reason. If `pre_filled_exclude_reason` is set on the suggestion, that text is pre-filled in the prompt.

---

### User Story 2 - Reverse triage decisions (Priority: P2)

After triaging, the user changes their mind. They can move shortlisted destinations back to review (if undecided), exclude shortlisted destinations (if a partner objects), or reconsider excluded destinations.

**Why this priority**: Vacation planning is iterative — partners discuss, change minds. Locking decisions in would force users to delete and re-create.

**Independent Test**: Shortlist a destination. Click Unreview to move it back to Pending Review. Then click Exclude. Verify the trip state reflects each move.

**Acceptance Scenarios**:

1. **Given** a destination is shortlisted, **When** the user clicks Unreview, **Then** it moves back to Pending Review.
2. **Given** a destination is shortlisted, **When** the user clicks Exclude with a reason, **Then** it moves to Excluded.
3. **Given** a destination is excluded, **When** the user clicks Reconsider with an optional note, **Then** it moves to Shortlisted (the original exclusion reason is dropped).

---

### User Story 3 - AI never re-suggests rejected destinations (Priority: P1)

If the user has already triaged a destination (in Pending, Shortlisted, or Excluded), the AI must not re-suggest it.

**Why this priority**: Re-suggesting rejected destinations breaks trust and wastes user attention. The original design hit this repeatedly.

**Independent Test**: Exclude a destination. Send "suggest more destinations". Verify that destination is not re-suggested.

**Acceptance Scenarios**:

1. **Given** a destination is in any of Pending/Shortlisted/Excluded, **When** the AI calls `search_destinations`, **Then** that destination is filtered out of the results.
2. **Given** the AI calls `suggest_for_review` for a destination already in any list, **When** the tool runs, **Then** it returns `{ "status": "rejected", "reason": "Already in <list> list" }` and the destination is NOT added.

---

### Edge Cases

- A user excludes a destination, then reconsiders it. The original exclusion reason is dropped (the user changed their mind).
- The AI suggests a destination by a slightly different name (e.g., "Algarve Coast" vs existing "Algarve, Portugal"). Name-based matching catches this in `_is_already_in_trip`.
- The AI uses `pre_filled_exclude_reason` for a recently-visited destination ("Visited in 2024 — revisit not soon"). The user clicks Exclude and the reason is pre-populated in the prompt.

## Requirements

### Functional Requirements

- **FR-001**: System MUST expose exactly one state-mutating tool to Claude (`suggest_for_review`). All other tools MUST be read-only.
- **FR-002**: `suggest_for_review` MUST insert into `suggested_destinations`, never directly into `shortlisted_destinations` or `excluded_destinations`.
- **FR-003**: System MUST provide UI actions for: Suggested → Shortlisted, Suggested → Excluded, Shortlisted → Excluded, Shortlisted → Suggested (Unreview), Excluded → Shortlisted (Reconsider).
- **FR-004**: All triage transitions MUST be triggered by explicit user action (HTTP POST), never by AI tool calls.
- **FR-005**: `suggest_for_review` MUST reject (without inserting) destinations already present in any of the three lists, by `region_lookup_key` OR by case-insensitive `destination_name` match.
- **FR-006**: `search_destinations` MUST filter out destinations already present in any of the three lists.
- **FR-007**: System MUST allow Claude to set a `pre_filled_exclude_reason` on a suggestion. The frontend MUST use this string as the default value in the exclude-reason prompt.
- **FR-008**: When moving Suggested → Shortlisted, the system MUST preserve `ai_reasoning`, `region_lookup_key`, and `scores_snapshot`.
- **FR-009**: When moving Suggested → Excluded, the system MUST preserve `ai_reasoning` (for context) and require a non-empty `reason`.
- **FR-010**: When moving Excluded → Shortlisted (Reconsider), the system MUST drop the original `reason` (it no longer applies) but allow a new optional `user_note`.

### Key Entities

- **SuggestedDestination**: A destination Claude has proposed for the user's review. Has `ai_reasoning`, optional `scores_snapshot`, optional `pre_filled_exclude_reason`. Lives until the user triages it.
- **ShortlistedDestination**: A destination the user has accepted for active consideration. Inherits reasoning and scores from the suggestion.
- **ExcludedDestination**: A destination the user has rejected, with a `reason`. Inherits the AI reasoning for context.

## Success Criteria

- **SC-001**: 100% of destinations entering Shortlisted or Excluded come from explicit user action — never from a tool call.
- **SC-002**: 0% of `suggest_for_review` calls succeed for destinations already in any list (they return `rejected`).
- **SC-003**: Each transition (shortlist, exclude, unreview, reconsider) is exposed as exactly one HTTP endpoint and one UI button.
- **SC-004**: Reverse transitions (unreview, reconsider) are tested and visible in the UI for each list.

## Assumptions

- Users will triage suggestions reasonably promptly — we don't expire suggestions.
- A suggestion contains enough context (reasoning + scores snapshot) for the user to triage without re-asking the AI.
- Pre-filled exclusion reasons are advisory; the user can always override.

## Constitution Check

- **Principle III (User Owns Decisions)**: ✅ This feature is the codification of this principle.
- **Principle V (Simple by Default)**: ✅ One tool replaced two; one queue table added; no new dependencies.
- All other principles unaffected.
