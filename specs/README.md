# Specs

Each folder under `specs/` is a feature-level design document, numbered by creation order. Specs follow the [spec-kit template](../.specify/templates/spec-template.md) and answer *why* and *what*. Code answers *how*.

| # | Feature | Status |
|---|---------|--------|
| [001](001-trip-planner-chatbot/spec.md) | Trip Planner Chatbot (initial design) | Implemented |
| [002](002-suggest-for-review-flow/spec.md) | Suggest-for-Review flow (replaces direct AI shortlisting) | Implemented |
| [003](003-conversations-and-history/spec.md) | Multi-conversation per trip + message editing | Implemented |
| [004](004-region-linking-and-fuzzy-matching/spec.md) | Region linking & fuzzy resolution | Implemented |
| [005](005-visit-history-filtering/spec.md) | Visit-history 3-tier filtering | Implemented |

## Adding a new spec

1. Create `specs/NNN-feature-slug/spec.md` from [`spec-template.md`](../.specify/templates/spec-template.md).
2. (Optional but recommended for non-trivial features) add `plan.md`, `data-model.md`, `research.md`, `contracts/`, `tasks.md`.
3. Include a Constitution Check section in `plan.md` evaluating each principle.
4. Add a row to the table above.

## Keeping specs current

When implementation diverges from a spec, update the spec **in the same change** as the code — do not let specs rot. See [CLAUDE.md → Documentation parity](../CLAUDE.md) for the rule.

If a feature is superseded, mark its `Status` as `Superseded by NNN` rather than deleting the spec.
