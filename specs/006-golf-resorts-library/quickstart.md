# Quickstart: Golf Courses & Resorts Library (spec 006)

Smoke test walkthrough for a fresh installation. Assumes the repo is cloned, `backend/venv` exists, and `ANTHROPIC_API_KEY` is exported.

## 1. Migrate schema and start the app

```bash
cd ~/PycharmProjects/VacationPlanner
./start.sh              # kills any process on :8000, launches uvicorn --reload
```

On first start after this feature ships, the app applies:

- `CREATE TABLE IF NOT EXISTS golf_resorts, golf_courses, entity_images`
- `ALTER TABLE trips ADD COLUMN activity_weights TEXT NOT NULL DEFAULT '{}'`
- `ALTER TABLE suggested_destinations ADD COLUMN resort_id INTEGER, course_id INTEGER`
- Same for `shortlisted_destinations`, `excluded_destinations`

No existing data is touched (Constitution Principle I).

Open http://localhost:8000 — the nav gains a new "Golf Library" entry.

## 2. Add a resort by URL

1. Click **Golf Library → Add**.
2. Entity type: **Resort**.
3. Paste URL: `https://www.monte-rei.com`.
4. Click **Fetch**. After ≤ 20 s, the form is pre-filled with name, country (PT), region (auto-linked to `PT:Algarve` if VacationMap has it), hotel type, price category, attached course(s) with par/length/architect, best months, and up to 5 image thumbnails.
5. Review, correct any hallucinated fields, click **Save**.

**Expected**: new resort appears in Golf Library → Resorts tab with a hero thumbnail. Source URL is visible on the detail page.

## 3. Add a course by name

1. **Golf Library → Add**.
2. Entity type: **Course**.
3. Type `Old Course, St Andrews`. Leave URL blank.
4. Click **Fetch**. Claude runs web search + extract.
5. Form pre-fills with holes=18, par=72, type=links, architect, year_opened, country=GB, plus source URLs.
6. Optional: the form may flag "This course appears to belong to the St Andrews Links complex — link to an existing resort?". Choose **Keep standalone** for this test.
7. Save.

**Expected**: appears in Courses tab with "Standalone" badge.

## 4. Browse, filter, sort

1. **Golf Library → Resorts tab**. Filter `country = Portugal`, `price = €€€€`. Sort by `rank_rating desc`.
2. Switch to **Courses tab**. Filter `country = Scotland`, `type = links`, `parent = any`. Sort by `rank_rating desc`.

**Expected**: the entries added in steps 2 and 3 match their respective filters; Unmatched-region entries show an "Unmatched region" badge in both list and detail views.

## 5. Full-text search

In either tab, type `monte` in the search box. Debounced after 200 ms; the list shrinks to matches against `name_norm` or `description`.

## 6. Seed the library (optional but recommended for realism)

```bash
cd backend
source venv/bin/activate
python scripts/seed_golf_library.py
```

Expect ~10–20 minutes runtime and ~$20–$40 of Anthropic API spend for the full ~120-entry curated list. The script prints a per-entry success/skip/failure summary. Re-running is safe and adds zero new entries.

**Expected after completion**: ≥ 90 European resorts + ≥ 15 iconic standalone courses in the library (SC-007).

## 7. Chatbot integration

### 7a. Resort-centric prompt

1. Create a new trip. Set `activity_weights = { golf: 100 }`.
2. Send: *"Golf trip in June, 5–7 days, luxury resorts in Europe."*

**Expected**: Claude calls `search_golf_resorts` with `month=6, price_category=["€€€€"], limit=10`, and the response cites specific resorts from the library by name with their ranks and course counts. Each suggested resort has a small thumbnail next to it in the message.

### 7b. Course-centric prompt

In the same trip or a new one: *"Best links courses in Scotland, ideally 18 holes, green fee under €300."*

**Expected**: Claude calls `search_golf_courses` with `country="GB", course_type=["links"], min_holes=18, max_green_fee_eur=300`. Response lists course names, par, length, architect, difficulty, rank.

### 7c. Named-entity lookup (library hit)

After seeding: *"What do you think of Monte Rei?"*

**Expected**: Claude calls `search_golf_resorts` with `name_query="Monte Rei"`. Response is prefixed with "from your library" and presents curated data (rank, courses, best months, price).

### 7d. Named-entity lookup (library miss)

Before seeding (or for a resort not in your list): *"What do you know about Pebble Beach?"*

**Expected**: Claude calls `search_golf_resorts` with `name_query="Pebble Beach"`, gets zero results, and replies with general-knowledge information **prefixed with "not in your curated library yet"** and a prompt to add it via the Add page.

## 8. Suggest-for-review with a specific resort

While the chatbot is proposing Monte Rei, watch for a `suggest_for_review` tool call that includes `resort_id=<monte_rei_id>`. The pending-review panel shows the suggestion linked to the specific resort, not just the region.

Shortlist it. Open the trip dashboard — the shortlisted destination row now shows both the region link and the resort link; clicking the resort badge jumps to the Golf Library detail page.

## 9. Prevent-delete check

1. Try to delete Monte Rei from Golf Library → Resorts → (its row) → Delete.
2. **Expected**: refused with a structured block — "2 attached courses, 1 shortlist reference in trip 'Summer Golf'". Each blocker has inline detach/delete actions.
3. Detach the courses (convert to standalone or delete them) and remove the shortlist entry.
4. Retry delete → now succeeds.

## 10. Link an unmatched resort

1. Add a resort whose extracted region doesn't match VacationMap (e.g., a resort in a region VacationMap doesn't track).
2. On the detail page, use the **Link to VacationMap region** autocomplete to pick the closest match.
3. **Expected**: VacationMap scores become visible at the bottom of the detail page (weather/cost/busyness/attractiveness for the linked region).

## 11. Images management

On any resort or course detail, use the **Images** panel:

- Add a new image URL (goes through SSRF guardrails same as page fetches).
- Reorder via drag or display_order input.
- Edit caption.
- Delete.

**Expected**: thumbnail in the list view updates (first image by `display_order`).

## Troubleshooting

- **Extraction returns `fetch_error` with "scheme not allowed"**: the URL is `ftp://...` or similar. Only `http`/`https` are accepted.
- **Extraction returns `fetch_error` with "host blocked"**: the URL resolves to a private IP. This is intentional SSRF protection (FR-005a).
- **Extraction returns `no_match`**: the name-only query found no plausible candidates. Try supplying a URL or a more specific name.
- **Seed script fails mid-run**: each entry is independent; the script logs the failure and continues. Re-run the script — idempotence via dedup will skip completed entries and retry the failed ones.
- **Chatbot doesn't cite library entries**: check the trip's `activity_weights`. If `golf < 30`, Claude only considers library tools when the user's free-text prompt explicitly mentions golf.
