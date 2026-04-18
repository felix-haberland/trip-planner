# VacationPlanner Constitution

This constitution governs the design and evolution of the **Trip Planner Chatbot** companion app to VacationMap. It supersedes all other practices and guides every spec, plan, and implementation decision.

## Core Principles

### I. User Data is Sacred (NON-NEGOTIABLE)

Trip plans, conversations, exclusion reasons, and user notes represent real planning effort by real people. We **never** delete or destructively migrate user data without explicit confirmation.

- `trips.db` is append-or-modify only. Schema migrations use `ALTER TABLE ADD COLUMN`.
- `vacation.db` is read-only — accessed only via `SELECT` through `vacationmap.py`.
- Deletes are user-initiated (UI confirm dialog or `DELETE` endpoint), never automated.
- Cascade deletes are scoped to the parent (deleting a trip removes its conversations/destinations; nothing wider).

### II. Transparent AI Configuration

The user must always be able to see and edit exactly what the AI is told.

- The travel profile lives in `profile.md` at the project root.
- The chatbot's behavioral instructions live in `instructions.md` at the project root.
- Both files are read fresh on every chat turn — edits take effect on the next message, no restart, no rebuild.
- System prompts are never hardcoded in Python. The only Python-side prompt content is the current trip state and visit history (which is data, not behavior).
- New AI behaviors are added by editing `instructions.md` first; code changes only when a new tool or data field is required.

### III. The User Owns the Decisions

Claude suggests; the user decides. The AI never directly shortlists or excludes a destination.

- Tool calls that modify the trip (`suggest_for_review`) only queue a destination into a "pending review" list.
- Triage actions (Shortlist / Exclude / Link region / Reconsider / Unreview) are exclusively user-initiated through the UI.
- Tools are read-only by default. Any new tool that mutates trip state must be reviewed against this principle and justified in the spec.

### IV. Stable Identifiers Across Boundaries

VacationMap is a separate app whose database may be re-imported. Companion-app references must survive that.

- Use `country_code:region_name` (e.g., `PT:Algarve`) as the stable lookup key everywhere a destination is referenced across DBs.
- Never store VacationMap primary keys (`region.id`) in `trips.db`.
- Snapshot scores at suggestion time (`scores_snapshot` JSON) so historical reasoning survives even if VacationMap data shifts.

### V. Living Documentation (NON-NEGOTIABLE)

Specs, this constitution, and `CLAUDE.md` must always reflect the current system. Documentation is updated **in the same change** as the code — never deferred, never allowed to rot.

- New feature or behavior change → add or amend a `specs/NNN-*/` folder. Create a new numbered folder for new features; mark superseded specs `Status: Superseded by NNN`.
- New rule, principle, or constraint → amend this constitution and bump its version (semver).
- New runtime convention, command, or learning → update `CLAUDE.md`.
- New endpoint, tool, or schema field → update `docs/api-reference.md` / `docs/data-model.md`.
- AI behavior change → update `instructions.md` first; code changes only when a new tool or data field is required (Principle II).

If you find documentation that is wrong, fix it — even if you didn't cause the drift. Stale docs are technical debt.

### VI. Simple by Default, Justify Complexity

This is a 2-user local app. Complexity must earn its place.

- No build step in the frontend (Vue 3 via CDN, plain HTML/CSS/JS).
- Single SQLite file per database — no Postgres, no migrations framework, no ORM gymnastics.
- One process serves both API and static frontend (uvicorn).
- No authentication, no multi-tenancy, no real-time sync. "Last write wins" is acceptable.
- New abstractions, libraries, or services must be justified in the spec's Complexity Tracking section.

## Technical Constraints

- **Language**: Python 3.11+ for backend; ES2020+ JavaScript for frontend.
- **Backend stack**: FastAPI, SQLAlchemy 2.x, Pydantic 2.x, Anthropic SDK. Adding a major dependency requires a spec amendment.
- **Frontend stack**: Vue 3 Composition API, marked.js for markdown. No npm, no bundler, no TypeScript.
- **Storage**: SQLite only. `trips.db` (read-write) and `vacation.db` (read-only).
- **AI model**: Claude Sonnet 4 (`claude-sonnet-4-20250514`). Model upgrades require an instruction-file review to ensure the new model still respects the existing rules.
- **Deployment**: Local or trusted private network. No public deployment without revisiting Principle V (which would force adding auth, rate limiting, secrets management, etc.).

## Development Workflow

### Specs precede code

Every non-trivial feature follows the spec-kit flow: `spec.md` → `plan.md` → optional `data-model.md` / `research.md` / `contracts/` → `tasks.md`. Specs live under `specs/NNN-feature-slug/`. The spec captures *why* and *what*; code captures *how*.

### Constitution Check gate

`plan.md` must include a "Constitution Check" section that explicitly evaluates the design against each principle above. Violations require a Complexity Tracking entry justifying the deviation.

### Code review checklist

Every PR or change must verify:

- [ ] No destructive operation on `trips.db` without user consent.
- [ ] No write to `vacation.db`.
- [ ] AI behavior changes are reflected in `instructions.md`, not hardcoded.
- [ ] New tool calls do not mutate trip state without user triage.
- [ ] New cross-DB references use `country_code:region_name`.
- [ ] No new build step, npm dependency, or runtime service introduced.
- [ ] Pre-commit (black + ruff) passes.

### Documentation parity

This is operationalized by Principle V. Every change must answer: "Does this contradict any spec, this constitution, or `CLAUDE.md`?" If yes, fix it in the same commit. If you spot pre-existing doc rot while working on something else, fix it too.

## Governance

This constitution supersedes any conflicting guideline in `CLAUDE.md`, `instructions.md`, or individual specs. When a conflict arises, the constitution wins until amended.

**Amendments**:

1. Propose the change in a spec or PR with rationale.
2. Update this file and bump the version (semver: MAJOR for principle removal/redefinition, MINOR for new principle, PATCH for clarification).
3. Update `Last Amended` date.
4. Re-evaluate any open spec's Constitution Check against the new version.

**Runtime guidance**: For day-to-day development conventions (commands, file layout, recent learnings), see `CLAUDE.md`. The constitution defines the rules; `CLAUDE.md` describes the current state.

**Version**: 1.1.0 | **Ratified**: 2026-04-18 | **Last Amended**: 2026-04-18
