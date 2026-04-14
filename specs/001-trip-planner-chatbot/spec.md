# Feature Specification: Trip Planner Chatbot

**Feature Branch**: `feat/001-trip-planner-chatbot`  
**Created**: 2026-04-14  
**Status**: Draft  
**Input**: User description: "A companion chatbot app to VacationMap that helps plan trips through conversational AI, suggesting destinations based on travel profile, visited countries, and trip-specific preferences (e.g. golf trip in June). Persists trip plans with included/excluded destinations and reasoning."

## Clarifications

### Session 2026-04-14

- Q: Should the app require authentication to protect access and Claude API usage? → A: No authentication — local/private network access only.
- Q: When the AI suggests a destination not in VacationMap, how should the app handle it? → A: Allow any suggestion, but clearly indicate "no scores available" for destinations not in the database.
- Q: How should the travel profile and chatbot instructions be managed? → A: Both must be stored as user-editable markdown files in the project, not hardcoded. The user must be able to read and edit them directly to see exactly what the AI is told.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Start a New Trip Plan (Priority: P1)

A user opens the companion app and creates a new trip plan. They describe what they're looking for — for example, "golf trip in June" or "adventurous hiking in October." The chatbot acknowledges the request, reads the couple's travel profile from the editable profile markdown file, checks which countries have already been visited (and their ratings), and suggests an initial set of destination candidates with detailed reasoning, scores, and pro/con arguments.

**Why this priority**: This is the core interaction loop — without the ability to start a conversation about a trip and receive AI-driven suggestions, the app has no value.

**Independent Test**: Can be fully tested by opening the app, creating a new trip, typing a trip description, and receiving destination suggestions with scores and reasoning.

**Acceptance Scenarios**:

1. **Given** the user has opened the app, **When** they create a new trip and describe it as "golf trip in June," **Then** the chatbot responds with at least 3 destination suggestions, each including the destination name, relevant scores (golf, weather, cost, busyness), and a pro/con summary explaining why the destination fits or doesn't perfectly fit the request.
2. **Given** the user has previously visited regions recorded in VacationMap with "visit_again: never," **When** those regions would otherwise match the trip criteria, **Then** they are excluded from suggestions (or flagged as previously visited with the user's rating).
3. **Given** the user describes a trip with specific constraints (e.g., "under 5 hours flight time"), **When** the chatbot generates suggestions, **Then** all suggestions respect the stated constraint and the chatbot explains how the constraint was applied.

---

### User Story 2 - Refine Trip by Adding or Excluding Destinations (Priority: P1)

After receiving initial suggestions, the user interacts with the chatbot to refine the trip. They can add a suggested destination to their shortlist or dismiss it for this trip. They can also ask for more suggestions, ask follow-up questions about a specific destination, or adjust the trip parameters. Each decision is persisted with a short note about why it was included or excluded.

**Why this priority**: The iterative refinement loop is what transforms a one-shot suggestion engine into a useful planning tool. Without persistence of decisions, the chatbot is just a search.

**Independent Test**: Can be tested by starting a trip, receiving suggestions, adding two destinations to the shortlist, excluding one with a reason, then verifying the trip state reflects all three actions.

**Acceptance Scenarios**:

1. **Given** the chatbot has suggested 5 destinations, **When** the user says "add Algarve to the list — great golf courses," **Then** the destination is saved to the trip's shortlist with the user's note and the scores are preserved alongside it.
2. **Given** the chatbot has suggested a destination, **When** the user says "not this time — too far," **Then** the destination is moved to the trip's excluded list with the reason "too far" visible.
3. **Given** the user has added 3 destinations and excluded 2, **When** they ask "what else do you have?", **Then** the chatbot suggests new destinations that are not already on either list, and explains how they compare to the current shortlist.

---

### User Story 3 - Resume an Existing Trip Plan (Priority: P1)

The user (or their partner) opens the app and sees a list of existing trip plans. They select one and immediately see the current state: shortlisted destinations with scores and reasoning, excluded destinations with dismissal reasons, and the original trip description. They can continue the conversation from where they left off.

**Why this priority**: Without persistence and retrieval, the app is a disposable chat. The ability to resume is what makes it a planning tool that both partners can use asynchronously.

**Independent Test**: Can be tested by creating a trip, adding/excluding destinations, closing the app, reopening it, selecting the trip, and verifying all state is intact and the conversation can continue.

**Acceptance Scenarios**:

1. **Given** the user previously created a trip plan with 3 shortlisted and 2 excluded destinations, **When** they reopen the app and select that trip, **Then** all shortlisted destinations appear with their scores, reasoning, and user notes, and all excluded destinations appear with their dismissal reasons.
2. **Given** a trip plan was last edited by the user's partner, **When** the user opens the same trip, **Then** they see all changes made by the partner and can continue the conversation.
3. **Given** the user opens an existing trip, **When** they send a new message like "actually, let's also consider beach destinations," **Then** the chatbot understands the existing trip context and provides new suggestions that complement (not duplicate) the current shortlist.

---

### User Story 4 - View Trip Dashboard with Scores and Comparisons (Priority: P2)

The user views a summary dashboard for a trip plan that shows all shortlisted destinations side by side with their key scores (weather, cost, busyness, golf, attractiveness, safety), the original reasoning for each, and any user notes. Excluded destinations are shown in a collapsed section with their short dismissal reasons.

**Why this priority**: The dashboard view is a reference artifact — useful once destinations have been curated, but not essential for the core conversation loop.

**Independent Test**: Can be tested by creating a trip with 4+ shortlisted and 2+ excluded destinations, then viewing the dashboard and verifying all scores, reasoning, and notes render correctly.

**Acceptance Scenarios**:

1. **Given** a trip has 4 shortlisted destinations, **When** the user views the trip dashboard, **Then** all destinations are shown with weather scores for the trip month, cost scores, busyness scores, and any activity-specific scores (e.g., golf), plus the AI reasoning for each.
2. **Given** a trip has 3 excluded destinations, **When** the user views the trip dashboard, **Then** excluded destinations appear in a separate collapsed section, each with a short text explaining why it was excluded.

---

### User Story 5 - Manage Trip Plans (Priority: P3)

The user can rename, archive, or delete trip plans. They can also see metadata such as creation date, last modified date, and the number of destinations in each state.

**Why this priority**: Housekeeping features that are necessary for long-term usability but not for core planning functionality.

**Independent Test**: Can be tested by creating multiple trips, renaming one, archiving one, deleting one, and verifying the trip list reflects all changes.

**Acceptance Scenarios**:

1. **Given** the user has 5 trip plans, **When** they view the trip list, **Then** each trip shows its name, creation date, last modified date, number of shortlisted destinations, and current status.
2. **Given** a trip plan exists, **When** the user deletes it, **Then** the trip and all its associated data (shortlisted destinations, excluded destinations, conversation history) are removed.

---

### Edge Cases

- What happens when the AI suggests a destination not in VacationMap? The system displays the suggestion with qualitative AI reasoning but clearly labels it as "unscored" — no numeric scores are shown. The destination can still be shortlisted or excluded.
- How does the system handle a trip description that is too vague (e.g., "go somewhere nice")? The chatbot should ask clarifying follow-up questions to narrow down preferences before suggesting destinations.
- What happens when all destinations matching the criteria have been visited with "visit_again: never"? The chatbot should inform the user that all matching destinations have been visited and suggest broadening criteria or reconsidering previously rated destinations.
- What if two users (the couple) are editing the same trip simultaneously? The system should show the most recent state on page load; real-time collaboration is out of scope for v1.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow users to create a new trip plan with a descriptive name and trip parameters (e.g., activity focus, target month, duration preferences).
- **FR-002**: System MUST integrate with an AI assistant (Claude) to generate destination suggestions based on the trip parameters, the couple's travel profile, and data from the VacationMap database.
- **FR-003**: System MUST read destination data (scores, weather, cost, busyness, attractiveness, golf, safety, tips, flight info) from the VacationMap database to inform AI suggestions.
- **FR-004**: System MUST read visit history from the VacationMap database to factor in previously visited regions and their ratings/revisit preferences.
- **FR-005**: System MUST allow users to add a suggested destination to the trip's shortlist, with an optional user note.
- **FR-006**: System MUST allow users to exclude a suggested destination from the trip, with a mandatory short reason.
- **FR-007**: System MUST persist all trip plans, including shortlisted destinations (with scores, AI reasoning, and user notes), excluded destinations (with dismissal reasons), and the conversation history.
- **FR-008**: System MUST display a list of all trip plans with metadata (name, created date, last modified, destination count).
- **FR-009**: System MUST allow users to open an existing trip plan and see the full state: shortlisted destinations with scores and reasoning, excluded destinations with reasons, and the ability to continue the conversation.
- **FR-010**: System MUST provide a dashboard view for a trip showing shortlisted destinations side by side with key scores for the trip's target month.
- **FR-011**: System MUST allow users to rename and delete trip plans.
- **FR-012**: System MUST use the user-provided Claude API key for AI interactions.
- **FR-013**: The AI assistant MUST consider safety scores as a hard constraint — destinations with low safety scores should be flagged or excluded, consistent with VacationMap's safety thresholds.
- **FR-016**: The AI assistant MAY suggest destinations not present in the VacationMap database. When it does, the system MUST clearly indicate that VacationMap scores are unavailable for that destination. The AI provides qualitative reasoning only — no fabricated numeric scores.
- **FR-014**: System MUST remain a separate application from VacationMap, sharing the database in read-only mode for destination and visit data while maintaining its own storage for trip plans and conversations.
- **FR-015**: System MUST NOT require authentication. The app is designed for local or private network access only; public internet deployment is out of scope.
- **FR-017**: The couple's travel profile MUST be stored in a user-editable markdown file within the project. The chatbot reads this file as context when generating suggestions. Changes to the file take effect on the next conversation message.
- **FR-018**: The chatbot's behavioral instructions (system prompt) MUST be stored in a user-editable markdown file within the project. This file defines how the chatbot reasons, structures suggestions, and interacts. The user must be able to see and modify exactly what the AI is instructed to do.

### Key Entities

- **Trip Plan**: Represents a vacation planning session. Contains a name, description/parameters (activity, month, constraints), creation and modification timestamps, and status. Owns a set of shortlisted destinations, excluded destinations, and a conversation history.
- **Shortlisted Destination**: A destination the user is considering for this trip. Links to a VacationMap region (via stable key `country_code:region_name`) when available. If the destination is not in VacationMap, the link is absent and scores are marked as unavailable. Contains the AI-generated reasoning, relevant scores snapshot for the trip month (if available), and optional user notes.
- **Excluded Destination**: A destination the user has dismissed for this trip. Links to a VacationMap region. Contains a short dismissal reason.
- **Conversation Message**: A single message in the trip's chat history. Has a role (user or assistant), content, and timestamp. The full conversation is persisted so the AI can maintain context when the trip is resumed.
- **Travel Profile**: A markdown file describing the travelers — who they are, activity preferences, comfort thresholds, travel constraints, and interests. Read by the chatbot as context for every suggestion. Edited directly by the user in a text editor.
- **Chatbot Instructions**: A markdown file defining the chatbot's behavior — how it should reason about destinations, structure its suggestions, weight different factors, and interact with the user. Fully transparent and editable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can create a new trip plan and receive the first set of destination suggestions within 15 seconds of describing their trip.
- **SC-002**: Each destination suggestion includes at least 4 relevant scores and a pro/con summary that references the user's specific trip criteria.
- **SC-003**: Users can resume any previously created trip plan and see the full state (shortlisted, excluded, conversation) within 3 seconds of selecting it.
- **SC-004**: Both partners can independently access and contribute to the same trip plan without data loss.
- **SC-005**: The trip dashboard displays all shortlisted destinations with comparable scores, enabling side-by-side decision-making without needing to re-ask the chatbot.
- **SC-006**: 90% of destination suggestions are backed by real VacationMap data (scores, weather, tips) rather than generic AI knowledge.

## Assumptions

- The VacationMap database (SQLite) is accessible from this companion app's environment (same machine or shared file path). The companion app reads VacationMap data in read-only mode.
- The couple's travel profile is maintained in a user-editable markdown file (e.g., `profile.md`) that the chatbot reads as context. This file describes who the travelers are, their preferences, constraints, and interests. The VacationMap scores and tips complement this profile but do not replace it.
- The user will provide their own Claude API key, which will be stored locally in the app configuration.
- The companion app maintains its own separate database/storage for trip plans, conversation history, and destination decisions — it does not write to the VacationMap database.
- Real-time collaborative editing between both partners is out of scope for v1; the system uses a "last write wins" model.
- The companion app runs locally or on a private network. Public deployment (e.g., Vercel) is out of scope for v1 — no authentication layer is required.
- The stable identifier pattern `country_code:region_name` is used to reference VacationMap destinations, ensuring resilience to database reimports.
