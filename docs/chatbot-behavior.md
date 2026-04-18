# Chatbot Behavior

This doc explains how the AI side of the app actually works: what Claude sees, what tools it can call, how state changes, and the principles that constrain it.

## System prompt assembly

Every user message triggers a fresh system prompt built by [`chat._build_system_prompt()`](../backend/app/chat.py). It concatenates four sections, separated by `---`:

1. **`instructions.md`** — behavioral rules (how to suggest, how many at a time, how to handle exclusions, etc.). User-editable.
2. **`profile.md`** — the couple's profile (preferences, constraints, interests). User-editable.
3. **Trip context** — current trip name/description/target month, plus three lists:
   - **Pending Review**: destinations Claude has suggested but the user hasn't triaged yet.
   - **Shortlisted**: destinations the user has accepted, with optional notes.
   - **Excluded**: destinations the user has dismissed, with reasons. Marked "RESPECT THESE DECISIONS — Read the reasons carefully — they reveal preferences that may apply to similar destinations too."
4. **Visit history** — every region in `region_visits` with rating + `visit_again` annotation. Includes a note explaining the `never` / `not_soon` / `few_years` / `anytime` semantics.

Because the prompt is rebuilt on every turn, editing `profile.md` or `instructions.md` takes effect on the next message — no restart, no rebuild.

## Conversation history

The full message history of the active conversation is sent on every turn. There is currently no summarization or trimming. With Claude Sonnet 4's context window this comfortably handles dozens of long messages plus tool results.

If a conversation grows uncomfortable, the user can start a new conversation under the same trip — the trip state (suggestions, shortlist, exclusions) is shared, but the chat history is fresh.

## Tool-use loop

After the API call:

```python
for _ in range(max_iterations=10):
    response = client.messages.create(model="claude-sonnet-4-20250514", ...)
    if response.stop_reason == "tool_use":
        # execute every tool_use block, append assistant + tool_result, loop
    else:
        # extract text, exit
```

Tool calls within a single user message all happen inside this loop. The 10-iteration cap is a safety stop — in practice, a single user turn rarely exceeds 3–4 iterations (e.g., one `search_destinations` + several `suggest_for_review` calls).

## Tools Claude can call

| Tool | Mutates state? | Purpose |
|------|----------------|---------|
| `search_destinations` | No | Score-ranked destination search filtered by month, activity focus, flight time, safety. Auto-filters destinations already in this trip. |
| `get_destination_details` | No | Full data for one region for a given month: scores, weather, tips, flight info, visit record. |
| `get_visit_history` | No | All visited regions with ratings and `visit_again` preferences. (Also surfaced in the system prompt — this tool is for explicit lookups.) |
| `get_trip_state` | No | Current pending/shortlisted/excluded for this trip. (Also in system prompt — explicit lookup tool.) |
| `suggest_for_review` | **Yes** | Queues a destination into the user's review list. Only state-mutating tool. |

### Why only `suggest_for_review` mutates state

An earlier design exposed `shortlist_destination` and `exclude_destination` as separate tools, letting Claude directly modify the trip. That removed user agency — Claude would shortlist things the user hadn't seen yet. We collapsed all suggestion-related tools into `suggest_for_review`, which only adds an entry to the "Pending Review" list. The user explicitly clicks Shortlist or Exclude in the UI.

This is constitution principle III ("The User Owns the Decisions") and is non-negotiable.

## Visit-history filtering

`vacationmap.search_destinations()` joins against `region_visits` and partitions results by `visit_again`:

- **`never`** — hard-filtered. The AI never sees these in search results.
- **`not_soon`** — filtered out of `results`, but high-scoring ones (top 5) are returned in `excluded_due_to_recent_visit`. The AI is instructed to mention them ("Algarve and Tenerife would also fit but are excluded due to recent visits").
- **`few_years`** — included in `results` with a `visit_again` annotation. The AI should only suggest these if they're an exceptional fit, and should pre-fill an exclusion reason.
- **`anytime`** / no record — included normally.

The system prompt also reproduces the full visit list with ratings and revisit preferences so Claude can reason about geographic and timing patterns ("you visited Thailand 6 months ago, so I'm avoiding nearby SE Asia").

## Region resolution (fuzzy matching)

When Claude calls `suggest_for_review`, it often provides a vague `destination_name` like `"Ireland"` or `"Costa del Sol, Spain"` without a `region_lookup_key`. [`tools._resolve_lookup_key()`](../backend/app/tools.py) runs a 6-step fallback chain:

1. **Exact region match** — `WHERE r.name = :name`.
2. **Region-name-as-country** — if `"Ireland"` is the name, treat it as a country and pick the highest `golf_score` region. *Runs before fuzzy region match to avoid `"Ireland"` matching `"Northern Ireland"` (in GB).*
3. **Country + region cross-match** — if both parts are given, fuzzy-match within that country.
4. **Country-name → best region** — if only a country is matchable, pick its top region.
5. **Fuzzy LIKE on region name** — last-resort substring match.
6. **Multi-word splitting** — for names like `"Portugal Golf Coast"`, try each word as a country, then remaining words against its regions.

When a fuzzy match changes the destination, `suggest_for_review` returns:
```json
{
  "fuzzy_matched": true,
  "matched_region": "Western Ireland",
  "other_regions_in_country": [...],
  "note": "Your suggestion was fuzzy-matched to 'Western Ireland'. Update your reasoning to mention this specific region."
}
```

The AI is instructed to acknowledge the resolution to the user in its next message so the user understands what was actually added.

## Score snapshotting

When `suggest_for_review` resolves a `region_lookup_key`, it also looks up the real scores for the trip's `target_month` from VacationMap (`_build_scores_from_db`). Those scores are stored as `scores_snapshot` JSON on the suggested/shortlisted destination row.

Why snapshot:
- VacationMap data may change between when Claude suggested a destination and when the user reviews their dashboard months later.
- The trip dashboard renders snapshotted scores, so the historical reasoning stays coherent.

If Claude provides AI-estimated scores in the tool input, we **prefer** real DB scores when available. AI estimates are only kept for destinations not in VacationMap.

## Target month detection

When a trip is created, `target_month` is `null`. After the first chat turn, [`chat._try_set_target_month()`](../backend/app/chat.py) scans the trip description for month keywords (`"june"`, `"jun"`, `"christmas"`, etc.) and sets `target_month` if found. This drives the default month for `search_destinations` and score snapshots.

If the description is ambiguous (e.g., "spring trip"), the AI is instructed to ask for clarification before searching.

## Safety, exclusions, and the "respect" rule

Two prompt mechanisms keep Claude from re-suggesting things the user has rejected:

1. **Search filtering** — `search_destinations` excludes any region already in the trip's pending/shortlist/excluded lists by `region_lookup_key`.
2. **Suggestion guard** — `suggest_for_review` rejects (returns `status: "rejected"`) if the destination by name or lookup key is already in any list.
3. **Prompt framing** — the trip context section tags Excluded as "RESPECT THESE DECISIONS" and asks Claude to read reasons for patterns ("too touristy" → avoid similar mainstream destinations).

This three-layer defense came from real cases where Claude would re-suggest excluded destinations or recommend the same place under a slightly different name.

## What the user can edit

| File | What it controls | When it takes effect |
|------|------------------|----------------------|
| `instructions.md` | All chatbot behavioral rules | Next message, no restart |
| `profile.md` | The couple's profile | Next message, no restart |

These are the two leverage points. New behaviors should land in `instructions.md` first; code changes only when a new tool, data field, or API endpoint is required (constitution principle II).
