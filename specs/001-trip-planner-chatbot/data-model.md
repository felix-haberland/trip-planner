# Data Model: Trip Planner Chatbot

**Date**: 2026-04-14  
**Feature**: [spec.md](spec.md)

## Overview

The companion app uses two databases:
1. **trips.db** (read-write) — owns trip plans, destinations, and conversation history
2. **vacation.db** (read-only) — VacationMap's existing database for regions, scores, and visits

Entities below are for `trips.db` only. VacationMap entities are documented in VacationMap's own codebase.

## Entities

### TripPlan

Represents a vacation planning session.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | Integer | PK, auto-increment | Internal ID |
| name | String | NOT NULL | User-given trip name (e.g., "Golf Trip June 2026") |
| description | String | NOT NULL | Trip description / parameters as entered by user |
| target_month | String | NULL | Target travel month (jan-dec, christmas, easter) |
| status | String | NOT NULL, default "active" | "active" or "archived" |
| created_at | DateTime | NOT NULL, auto | Creation timestamp |
| updated_at | DateTime | NOT NULL, auto-update | Last modification timestamp |

**Relationships**: Has many ShortlistedDestination, ExcludedDestination, ConversationMessage.

**State transitions**: `active` → `archived` (reversible)

---

### ShortlistedDestination

A destination the user is considering for a trip.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | Integer | PK, auto-increment | Internal ID |
| trip_id | Integer | FK → TripPlan.id, NOT NULL | Parent trip |
| region_lookup_key | String | NULL | VacationMap stable key (e.g., "PT:Algarve"). NULL if not in VacationMap |
| destination_name | String | NOT NULL | Display name (e.g., "Algarve, Portugal") |
| ai_reasoning | Text | NOT NULL | AI-generated pro/con reasoning |
| scores_snapshot | Text | NULL | JSON blob of scores at time of suggestion (weather, cost, busyness, etc.). NULL for unscored destinations |
| user_note | String | NULL | Optional user-added note |
| added_at | DateTime | NOT NULL, auto | When added to shortlist |

**Uniqueness**: (trip_id, region_lookup_key) is unique when region_lookup_key is not NULL. A destination can only be shortlisted once per trip.

**Validation**: destination_name is always required. region_lookup_key is NULL for destinations not in VacationMap.

---

### ExcludedDestination

A destination the user has dismissed for a trip.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | Integer | PK, auto-increment | Internal ID |
| trip_id | Integer | FK → TripPlan.id, NOT NULL | Parent trip |
| region_lookup_key | String | NULL | VacationMap stable key. NULL if not in VacationMap |
| destination_name | String | NOT NULL | Display name |
| reason | String | NOT NULL | User-provided dismissal reason |
| ai_reasoning | Text | NULL | AI reasoning at time of suggestion (preserved for context) |
| excluded_at | DateTime | NOT NULL, auto | When excluded |

**Uniqueness**: (trip_id, region_lookup_key) is unique when region_lookup_key is not NULL.

---

### ConversationMessage

A single message in a trip's chat history.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | Integer | PK, auto-increment | Internal ID |
| trip_id | Integer | FK → TripPlan.id, NOT NULL | Parent trip |
| role | String | NOT NULL | "user" or "assistant" |
| content | Text | NOT NULL | Message content |
| created_at | DateTime | NOT NULL, auto | Message timestamp |

**Ordering**: Messages are ordered by created_at ASC within a trip.

---

## Read-Only Access: VacationMap Entities

The companion app reads these VacationMap tables (never writes):

- **countries**: id, name, code
- **regions**: All fields (scores, weather, tips, flight info, static attributes)
- **region_visits**: Visit records with ratings and revisit preferences
- **list_regions** / **lists**: Destination lists (for context)

Access is via a separate read-only SQLAlchemy engine pointing to VacationMap's `vacation.db`.

## Entity Relationship Diagram

```
trips.db                              vacation.db (read-only)
┌──────────────────┐                  ┌─────────────┐
│ TripPlan         │                  │ countries    │
│ ├─ id (PK)       │                  │ regions      │
│ ├─ name          │                  │ region_visits│
│ ├─ description   │                  │ lists        │
│ ├─ target_month  │                  └─────────────┘
│ ├─ status        │                        ▲
│ ├─ created_at    │                        │
│ └─ updated_at    │                   (lookup via
├──────────────────┤                region_lookup_key)
│ 1:N              │                        │
▼                  ▼                        │
┌──────────────┐ ┌──────────────────┐       │
│ Conversation │ │ Shortlisted      │───────┘
│ Message      │ │ Destination      │
│ ├─ role      │ │ ├─ lookup_key ──────→ "CC:Region"
│ ├─ content   │ │ ├─ scores_snapshot│
│ └─ created_at│ │ └─ user_note     │
└──────────────┘ └──────────────────┘
                 ┌──────────────────┐
                 │ Excluded         │
                 │ Destination      │
                 │ ├─ lookup_key ──────→ "CC:Region"
                 │ └─ reason        │
                 └──────────────────┘
```

## Cascade Behavior

When a TripPlan is deleted, all related ShortlistedDestinations, ExcludedDestinations, and ConversationMessages are cascade-deleted.
