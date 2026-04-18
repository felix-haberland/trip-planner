# Feature Specification: Multi-Conversation per Trip + Message Editing

**Feature Branch**: `feat/003-conversations-and-history`
**Created**: 2026-04-18
**Status**: Implemented (retroactive spec)
**Input**: Allow multiple parallel conversations per trip, message editing/deletion, and conversation archival.

## Summary

The original 001 design had one flat `ConversationMessage` list per trip. In practice, users wanted to:

1. Start a fresh conversation thread when changing trip focus (e.g., "Main" vs "October alternatives") without polluting the original chat.
2. Edit or delete individual messages (typo fixes, removing accidental sends, pruning irrelevant turns).
3. Archive old conversations without losing them.

This feature introduces a `Conversation` entity between `TripPlan` and `ConversationMessage`, while keeping the trip-level destination state shared across all conversations.

## User Scenarios & Testing

### User Story 1 - Run multiple conversations on the same trip (Priority: P1)

The user is planning a trip and gets a set of suggestions. They want to explore an alternative angle (different month, different focus) without losing their existing chat. They create a new conversation under the same trip. The new conversation has fresh chat history but shares the trip's Pending/Shortlisted/Excluded lists.

**Why this priority**: Conversations grow long; restarting context is a normal planning move. Without parallel conversations, users either lose context or create duplicate trips.

**Independent Test**: Open a trip with chat history. Click "New conversation". Verify the new conversation has 0 messages but the destination sidebar still shows all triaged destinations.

**Acceptance Scenarios**:

1. **Given** a trip exists with one conversation and several messages, **When** the user creates a new conversation named "October alternatives", **Then** that conversation appears as a tab and has 0 messages, but the destination sidebar (Pending/Shortlisted/Excluded) is unchanged.
2. **Given** a trip has 2 conversations, **When** the user switches between them, **Then** the chat history reloads but the destination sidebar stays the same.
3. **Given** a trip has 2 conversations and the user sends a message in conversation B, **When** the AI responds, **Then** the message and response are persisted to conversation B only — conversation A is unaffected.

---

### User Story 2 - Archive and rename conversations (Priority: P2)

After completing a planning thread, the user archives it to declutter the tab list, but wants to keep it for reference. They can also rename conversations to give them meaningful labels.

**Why this priority**: Tab clutter degrades the UX; renaming makes archived conversations findable later.

**Independent Test**: Archive a conversation. Verify it disappears from the active tabs but appears under "Archived". Unarchive it. Verify it returns.

**Acceptance Scenarios**:

1. **Given** an active conversation, **When** the user clicks Archive, **Then** it moves to the Archived section and is hidden from the active tab bar by default.
2. **Given** an archived conversation, **When** the user clicks Unarchive, **Then** it returns to the active tabs.
3. **Given** any conversation, **When** the user renames it, **Then** the new name appears in the tab bar.
4. **Given** any conversation, **When** the user deletes it (with confirmation), **Then** it and all its messages are permanently removed. The trip's destination state is NOT affected.

---

### User Story 3 - Edit and delete individual messages (Priority: P2)

The user notices a typo in a message they sent, or wants to remove an off-topic exchange. They can edit any message's content or delete it entirely.

**Why this priority**: Long planning threads accumulate noise. Without editing, users lose precision; without deleting, they can't prune.

**Independent Test**: Send a message with a typo. Click edit, fix the typo, save. Verify the message updates. Delete a different message; verify it disappears.

**Acceptance Scenarios**:

1. **Given** any message in a conversation, **When** the user edits its content and saves, **Then** the new content is persisted and re-rendered.
2. **Given** any message, **When** the user clicks delete and confirms, **Then** the message is removed from history.
3. **Given** an assistant message containing questions, **When** the user opens the "zoom" overlay, **Then** the questions are parsed and the user can answer them inline. Submitting sends the structured answers as a new user message.

---

### Edge Cases

- A user deletes the last message in a conversation. The conversation remains (it can have 0 messages).
- A user deletes a conversation that's currently active in the UI. The frontend switches to the next active conversation; if none, it shows an empty state.
- The "Main" conversation cannot be auto-deleted, but can be manually deleted by the user (with confirmation).
- Editing an old message does not retroactively change Claude's past behavior — Claude only sees the conversation history as it stands when the next message is sent.

## Requirements

### Functional Requirements

- **FR-001**: System MUST allow a TripPlan to have multiple Conversation entities.
- **FR-002**: System MUST auto-create a "Main" conversation when a trip is opened for the first time.
- **FR-003**: System MUST scope ConversationMessage rows to a single Conversation. Trip-level destination state (Suggested/Shortlisted/Excluded) MUST be shared across all conversations of the same trip.
- **FR-004**: System MUST expose endpoints to create, rename, archive, unarchive, and delete conversations.
- **FR-005**: Deleting a Conversation MUST cascade-delete its messages but MUST NOT affect the trip's destinations.
- **FR-006**: System MUST allow editing and deleting any individual ConversationMessage (user or assistant).
- **FR-007**: When sending a chat message, the chat endpoint MUST be scoped to a Conversation (`/api/conversations/{conv_id}/messages`), not a Trip.
- **FR-008**: The conversation tab list MUST pin "Main" first; remaining conversations sort by `created_at ASC`.
- **FR-009**: Archived conversations MUST be hidden by default but reachable via a toggle in the UI.
- **FR-010**: For backward compatibility, existing `conversation_messages` rows from the pre-Conversation era MAY have NULL `conversation_id` and a populated `trip_id`. New writes MUST always set `conversation_id`.

### Key Entities

- **Conversation**: A chat thread under a trip. Has `name`, `status` (active/archived), `created_at`. Owns its messages but not the trip's destinations.
- **ConversationMessage**: Unchanged in shape, but now scoped to `conversation_id` instead of `trip_id`.

## Success Criteria

- **SC-001**: A trip with N conversations preserves all messages independently after switching between conversations.
- **SC-002**: Deleting a conversation removes only its messages, leaving the trip's destination state intact.
- **SC-003**: Editing or deleting a message updates persistence within 500ms of the click.
- **SC-004**: The conversation tab UI remains usable with 5+ conversations per trip.

## Assumptions

- Users will not create dozens of conversations per trip — typical use is 1–3.
- Edits to past messages are intentional and the user understands they alter what Claude sees on the next turn.
- Users do not need a real-time multi-user view of conversations (last write wins).

## Constitution Check

- **Principle I (Data Safety)**: ✅ Conversation deletes require user confirmation; cascade is scoped (messages only, not destinations).
- **Principle V (Simple by Default)**: ✅ One new table (`conversations`); the messages table grew one nullable column. No new dependencies.
- All other principles unaffected.
