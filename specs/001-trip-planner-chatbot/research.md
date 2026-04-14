# Research: Trip Planner Chatbot

**Date**: 2026-04-14  
**Feature**: [spec.md](spec.md)

## R1: Claude API Integration for Conversational Trip Planning

**Decision**: Use the Anthropic Python SDK (`anthropic`) with the Messages API and tool use (function calling) to let Claude query VacationMap data on demand during conversations.

**Rationale**: Tool use allows Claude to request specific data (scores for a region/month, visit history, filtered destination lists) rather than dumping the entire database into the context window. This keeps token usage efficient and lets the AI decide what data it needs based on the conversation. The Messages API supports multi-turn conversations natively.

**Alternatives considered**:
- *Pre-load all data into system prompt*: Rejected — VacationMap has 80+ columns per region across 12 months. For 100+ regions, this would consume most of the context window and be wasteful when only a subset is relevant.
- *Use VacationMap's HTTP API*: Considered — the companion app could call VacationMap's REST endpoints. However, the companion app should work independently (VacationMap server doesn't need to be running). Reading the SQLite DB directly is simpler and more reliable for a local app.

## R2: Conversation Context Management

**Decision**: Persist full conversation history in the database. When sending to Claude, include the system prompt (instructions + profile + current trip state) plus the full message history. If the conversation exceeds token limits, summarize older messages using a condensation step.

**Rationale**: For a personal tool with conversations of ~20-50 messages, full history easily fits within Claude's context window. The system prompt with profile, instructions, and trip state (shortlisted/excluded destinations) provides Claude with all needed context on each turn. A summarization fallback handles edge cases of very long planning sessions.

**Alternatives considered**:
- *Send only last N messages*: Rejected — loses context about earlier decisions and reasoning.
- *Always summarize*: Rejected — unnecessary for typical conversation lengths and loses nuance.

## R3: Database Strategy for Trip Data

**Decision**: Use a separate SQLite database for trip plan data (e.g., `trips.db`), managed by SQLAlchemy with the same patterns as VacationMap. Read VacationMap's `vacation.db` in read-only mode via a second database connection.

**Rationale**: SQLite is the natural choice to align with VacationMap's tech stack. A separate database file keeps the two apps independent — the companion app never modifies VacationMap data, and VacationMap remains unaware of the companion. Two SQLAlchemy engines (one read-write for trips, one read-only for VacationMap) is straightforward.

**Alternatives considered**:
- *Single shared database with new tables*: Rejected — couples the apps, risks accidental writes to VacationMap tables, complicates VacationMap's reimport process.
- *JSON files for trip persistence*: Rejected — harder to query, no relationship integrity, doesn't scale well for conversation history.

## R4: Tool Definitions for Claude

**Decision**: Define these tools for Claude to call during conversations:

1. **search_destinations**: Query VacationMap regions by month with optional filters (activity focus, flight time max, min safety score, exclude visited). Returns top N results with scores.
2. **get_destination_details**: Get full details for a specific region (all scores for a month, tips, flight info, visit history).
3. **get_visit_history**: Retrieve all visited regions with ratings and revisit preferences.
4. **shortlist_destination**: Add a destination to the trip's shortlist with reasoning and scores.
5. **exclude_destination**: Mark a destination as excluded with a reason.
6. **get_trip_state**: Retrieve current shortlisted and excluded destinations for the active trip.

**Rationale**: These tools give Claude structured access to exactly the data it needs. The search tool leverages VacationMap's scoring algorithm (same composite score calculation). The shortlist/exclude tools let Claude take actions that persist state, creating a tight interaction loop.

**Alternatives considered**:
- *Raw SQL access*: Rejected — too powerful, risk of injection or unintended queries.
- *Fewer tools with larger payloads*: Rejected — forces Claude to process unnecessary data.

## R5: Frontend Chat Architecture

**Decision**: Use Vue.js 3 via CDN (aligned with VacationMap) with a simple chat interface. The frontend sends messages to the backend, which orchestrates Claude API calls and returns responses. Static HTML/CSS/JS — no build step.

**Rationale**: Matches VacationMap's approach exactly (Vue 3 CDN, static files, no npm/build). Keeps the companion app lean. The backend handles all AI orchestration; the frontend is a thin chat UI plus a trip dashboard view.

**Alternatives considered**:
- *React or Svelte*: Rejected — tech stack alignment requirement.
- *npm-based Vue with build step*: Rejected — VacationMap uses CDN; maintaining consistency keeps both apps approachable.

## R6: Profile and Instructions File Strategy

**Decision**: Store two markdown files in the project root:
- `profile.md` — the couple's travel profile (who they are, preferences, constraints)
- `instructions.md` — the chatbot's behavioral instructions (how to reason, suggest, interact)

The backend reads these files at each conversation turn and includes their content in Claude's system prompt. No caching — changes take effect immediately.

**Rationale**: The user explicitly requested transparent, editable markdown files. Reading at each turn (not cached) means edits take effect on the very next message without restarting the app. The files are small (likely <2KB each), so the read cost is negligible.

**Alternatives considered**:
- *Database-stored config*: Rejected — not transparent, requires UI to edit.
- *Cached with reload endpoint*: Rejected — unnecessary complexity for local use.
