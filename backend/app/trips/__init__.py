"""Trip planning subsystem.

- models.py      — TripPlan, SuggestedDestination, ShortlistedDestination,
                   ExcludedDestination, Conversation, ConversationMessage
- schemas.py     — Pydantic types for trip/message/conversation I/O
- crud.py        — DB operations for trip planning
- chat.py        — Claude conversation loop + system prompt assembly
- tools.py       — trip-planning Claude tools (search_destinations, suggest_for_review, etc.)
- vacationmap.py — read-only VacationMap access + scoring
- routes.py      — FastAPI APIRouter with all /api/trips/* and /api/vacationmap/* endpoints
"""
