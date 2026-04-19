"""Yearly Vacation Planner (spec 007).

A year-plan is a parallel-to-trips planning layer: user-defined Slots (time
windows) hold TripOption candidates that progress through the same
suggest/shortlist/exclude lifecycle as destinations. Slots can be committed
into concrete TripPlan rows when the user is ready to plan a specific trip.

Package layout mirrors `app/trips/` and `app/golf/`: models, schemas, crud,
routes, tools, chat. All writes go to the shared `trips.db` via `TripsBase`.
"""
