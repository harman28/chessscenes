# chessscenes — CLAUDE.md

## What this is

A Flask web app that maps chess venues around the world — clubs, bars, outdoor boards, memorials, museums. Lives at a Railway-hosted URL, deployed automatically on push to `main`.

---

## Tech stack

- Python / Flask
- SQLite (`chess.db`) — committed to the repo as the source of truth
- Deployed on **Railway** — auto-deploys on every push to `main`
- `Procfile`: `web: python3 app.py`

---

## Database

`chess.db` is checked into git. Any changes to the database must be committed and pushed to take effect in production.

### Tables

- `venue_directory` — the main public-facing table. Columns: `id`, `name`, `labels`, `address`, `city`, `lat`, `lng`, `gmaps`, `link`, `image`, `note`
- `venues` — venues used for scheduled events
- `events` — scheduled events with community/venue links
- `event_recurrences` — days of the week an event recurs
- `communities` — chess communities/clubs

### Labels used in venue_directory

`chess club`, `chess bar`, `chess meetup`, `chess board`, `chess shop`, `chess museum`, `chess memorial`

---

## Deployment

```
git add chess.db
git commit -m "..."
git push origin main
```

Railway picks up the push and redeploys automatically. No manual trigger needed.

---

## Data import

`import_venues.py` — one-off script used to bulk-import venues from the CSV. Matches on `name + city` to avoid duplicates, updates existing rows and inserts new ones.

---

## Reviewing scout candidates

`pending_venues.json` is populated daily by the GitHub Actions scout agent (`scout.py`). At the start of each session, check if there are pending venues: read `pending_venues.json` and if it's non-empty, present the candidates to Harman one by one (name, city, note, link) and ask approve/reject/edit. On approval, add the row to the CSV, remove it from the JSON, commit both, and push. On reject, just remove it from the JSON and commit.

**Cap at 5 reviews per session.** After the 5th, commit progress and tell Harman how many remain.

---

## Adding new venues or events (mobile screenshot workflow)

Harman may send a screenshot of a chess venue or event listing (from Instagram, Google Maps, a website, etc.) and ask you to add it. When this happens:

1. **Extract from the screenshot**: name, city, labels (pick from the list above), coordinates (lat/lng — look them up via the note/address if not visible), note (brief description of what it is / when it meets), Google Maps link, website/Instagram link, image URL (imgur preferred — ask Harman if none available), days (comma-separated day names if it recurs on specific days, e.g. `Tuesday` or `Friday, Saturday`).

2. **Add a row to the CSV** — **important:** quote any field that contains commas, including Google Maps URLs (e.g. `"https://maps.google.com/place/628+SE+Belmont+St,+Portland,+OR"`). Unquoted commas in URLs corrupt the column alignment. at `/Users/harmansingh/workplace/chess scenes project/chessscenes/Chess Scenes (Public) - chess_scenes_venues.csv`. Column order: `name,labels,city,coordinates,note,gmap,link,image,days,id`. Leave `id` empty. Quote the coordinates field: `"lat, lng"`. Quote the days field if multiple: `"Monday, Wednesday"`.

3. **Commit and push**:
   ```
   git add "Chess Scenes (Public) - chess_scenes_venues.csv"
   git commit -m "Add <name> (<city>)"
   git push origin main
   ```

Railway auto-deploys on push. `seed_directory()` runs on startup and reseeds `venue_directory` from the CSV. The new entry will appear on the map within ~30 seconds.

**Principle**: the site tells you where to go to find chess. This includes clubs, bars (with days they have chess), outdoor boards, museums, shops, memorials. If something has `days` set, it shows up in the events sidebar as well as on the map.

---

## Shareable pages and social previews

Every URL on the site used to render the same generic `index.html` with no per-page `og:*`
tags — a WhatsApp/social share of any link looked identical and generic no matter what it
actually pointed at. Fixed by giving venues, events, cities, and the homepage each their own
server-rendered `<meta>` tags (Jinja auto-escapes these, unlike chess-library-api's manual
string-substitution approach — no special escaping needed here).

- `/venue/<slug>` and `/event/<id>` — pre-existing, unchanged. Per-item `og:image` uses the
  venue/community's own photo.
- **`/city/<slug>`** — new. Renders the same map/sidebar app, pre-filtered to that city
  (`initial_data.city` reuses the existing venue/event deep-link mechanism that pre-selects
  `#city-select`). Its `og:image` is a **generated static map** (see below), not a stock
  photo — deliberately, since there's no single real photo that represents "a city," and a
  stock image would risk implying a specific place. `slug` is computed via the existing
  `slugify()` (same one used for venue slugs) against each city's real name; there's no
  stored city-slug column, `find_city_by_slug()` just scans `SELECT DISTINCT city` and
  matches. `/api/cities` now returns `[{name, slug}, ...]` instead of a plain string array
  (the only consumer, `loadCities()` in `templates/index.html`, was updated to match) so the
  frontend's "Share this city ↗" link (`#share-city-link`, next to the city/date picker) can
  build the right URL without re-deriving the slug logic in JS.
- **`/` (homepage)** — new. Same idea as city pages: `og:image` is a static map of *every*
  venue globally rather than a stock photo, so a bare link share still looks like something
  real and specific ("163 places to find chess around the world…") instead of one fixed
  generic image.

**Static map generation** (`render_pin_map()` in `app.py`, served via `/map.png` and
`/city/<slug>/map.png`): fetches real OpenStreetMap raster tiles (`tile.openstreetmap.org`,
with an identifying `User-Agent` per their usage policy) covering the venues' bounding box,
stitches them into a 1200×630 canvas via Pillow, then draws a solid maroon/cream pin
(`MAP_PIN_COLOR`/`MAP_PIN_OUTLINE`, matching `--maroon`/`--cream` in `templates/index.html`)
at each venue's projected pixel position using standard Web Mercator tile math
(`_lonlat_to_pixel`/`_fit_zoom`). A single venue (or all-identical coordinates) gets padded
by ~0.02° so it doesn't degenerate to a single dot with no context. Results are cached
in-memory (`_map_image_cache`, keyed by city + point count + sorted coordinates so it
self-invalidates when venues are added/moved) — safe because this app runs as a single
process (`Procfile`: `python3 app.py`, no gunicorn workers), unlike chess-library-api's
Postgres-backed rate limiter which had to account for multiple workers. Don't add a
persistent/disk cache for this — it's meant to regenerate cheaply on the next deploy, and a
committed PNG per city would go stale silently as venues get added.

**Dependency added**: `Pillow` (requirements.txt) — same rasterization role it plays in
chess-library-api's board-preview PNGs, no new pattern introduced.
