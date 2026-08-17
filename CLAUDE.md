# chessscenes — CLAUDE.md

## What this is

A Flask web app that maps chess places around the world — clubs, bars, outdoor boards,
memorials, museums. Lives at a Railway-hosted URL, deployed automatically on push to
`main`.

**Staging first, always.** The Railway project also has a `chessscenes-rebuild` service
(same project, its own URL) — push non-trivial changes there and have Harman test before
merging to `main`, which redeploys the real `web` service at chessscenes.com. Never push
straight to `main` for anything beyond a one-line data fix.

---

## Tech stack

- Python / Flask
- SQLite (`chess.db`) — **not committed to git.** It's fully derived from the two source
  files below and rebuilt from scratch on every process start (`init_db()` +
  `seed_places()` + `seed_communities_and_events()` in `app.py`'s `__main__` block). Never
  hand-edit rows in `chess.db` expecting them to survive a deploy — edit the source files.
- Deployed on **Railway** — auto-deploys on every push to `main`
- `Procfile`: `web: python3 app.py`

---

## Data model

Three concepts, same names in the database, the API, and the URLs:

- **`places`** — every physical chess spot: clubs, bars, outdoor boards, museums, shops,
  memorials. Just "what and where." `lat`/`lng` are **required** — every place needs real
  coordinates, no exceptions.
- **`communities`** — a group that runs events (name + image).
- **`events`** — a recurring or one-off time slot. Usually tied to a `place_id`, but can
  instead carry its own standalone location (`standalone_name`/`standalone_address`/
  `standalone_city`/`standalone_lat`/`standalone_lng`/`standalone_gmaps`) when a roaming
  community (Barblitz) plays somewhere that isn't otherwise a chess place — this is what
  keeps a one-off bar from getting a permanent pin just because a traveling event used it
  once. `event_recurrences` holds the day-of-week rows for a recurring event;
  `specific_date` is used instead for a one-off.

A place with no events is map furniture only (grey pin). A place with one or more events is
filterable by day (red pin on days it has something on). The scenes list and the map's red
pins are driven off the exact same `places`/`events` join, filtered by the same city + day —
they can't disagree about what's showing.

### Durable source files

`chess.db` has no unique state of its own — these two committed files are the real source
of truth, reseeded into `chess.db` on every startup:

- **`Chess Scenes (Public) - chess_scenes_venues.csv`** — one row per place. Columns:
  `name,labels,city,coordinates,note,gmap,link,image,slug,id`. `slug` is required and must
  be unique — generate it the same way `slugify()` in `app.py` does (lowercase, spaces →
  hyphens, strip punctuation; append the city if the base slug collides). `id` is unused,
  leave empty. Quote any field containing a comma, including Google Maps URLs and multi-word
  `coordinates`/`labels` values.
- **`chess_scenes_events.json`** — `{"communities": {name: image_url, ...}, "events": [...]}`.
  Each event object: `place_slug` (referencing a row in the CSV above) **or**
  `standalone_name`/`standalone_address`/`standalone_city`/`standalone_lat`/
  `standalone_lng`/`standalone_gmaps` when there's no fixed place, plus `community` (name,
  or `null`), `title`, `time`/`time_end`, `format_tag`, `external_link`, `notes`, `days`
  (list of day names, for recurring events) or `specific_date` (`"YYYY-MM-DD"`, for one-off
  events), and `active` (set `false` to archive without deleting).

### Labels used on places

`chess club`, `chess bar`, `chess meetup`, `chess board`, `chess shop`, `chess museum`, `chess memorial`

---

## Deployment

```
git add "Chess Scenes (Public) - chess_scenes_venues.csv" chess_scenes_events.json
git commit -m "..."
git push origin main   # or push to a branch and deploy to chessscenes-rebuild first
```

Railway picks up the push and redeploys automatically; `chess.db` is rebuilt fresh from
these two files on boot. No manual trigger, and nothing to do with `chess.db` itself.

---

## Adding a place or event (conversational workflow)

Harman may ask in a chat session, or send a screenshot of a chess venue/event listing
(Instagram, Google Maps, a website, etc.), and ask you to add it. There's no admin-UI step
required — edit the two source files directly:

1. **New place** (a physical spot that doesn't exist yet): add a row to the places CSV.
   Extract name, city, coordinates (look them up via the address/note if not visible in the
   screenshot), a label from the list above, a note, Google Maps link, website/Instagram
   link, an image URL (imgur preferred — ask Harman if none available), and generate a
   unique `slug`. Coordinates are mandatory — don't add a place without them.
   **Don't guess a label from the venue/community name** — during the places/events
   migration, 4 of 9 newly-created places got mislabeled this way (e.g. "KLABU Clubhouse"
   hosting "Amsterdam Spirit Chess **Club**" looked like `chess club`, but the actual
   gathering is casual, not a formal membership club — it should be `chess meetup`). The
   reliable signal is the *event's* own `format_tag`: `"Club night"` means a real club
   (schaakvereniging-style, dues/league play), anything else (`"Casual"`, `"Open play"`,
   etc.) doesn't, regardless of what the name says.
2. **New event** at an existing place: add an object to `chess_scenes_events.json`'s
   `events` list with that place's `place_slug`, the community (if any), and either `days`
   (recurring) or `specific_date` (one-off).
3. **New event with no fixed place** (a roaming community playing somewhere that isn't
   otherwise a chess place — e.g. a Barblitz tournament at a bar with no other chess
   connection): add the event with `standalone_name`/`standalone_city`/`standalone_lat`/
   `standalone_lng` instead of a `place_slug`. This is deliberate — it keeps that bar off
   the map as a permanent pin; it'll only show up as a pin on the day the event happens.
4. **Commit and push** both changed files together (see Deployment above).

**Archiving**: don't delete an event that's no longer active — set `"active": false` on it
instead, so the history/reasoning stays in the file (e.g. Chess & Beer, archived 2026-08-17
because the meetup stopped running — its venue, Cafe De Balie, was removed from `places`
entirely rather than archived, since it was never a chess place on its own, only ever
Chess & Beer's venue; the archived event keeps Cafe De Balie's location as a standalone
field instead of a `place_id`).

**`migrate_to_places_schema.py`** is a one-off migration script, already run (2026-08-17) —
it's kept as a historical record of exactly what the old `venues`/`venue_directory`/`events`
data became, not something to run again.

---

## Reviewing scout / scraper candidates

Three sources feed pending-review files, all reviewed the same way: read the file, present
each candidate to Harman one by one, approve/reject/edit, then commit. **Cap at 5 reviews
per session** — after the 5th, commit progress and tell Harman how many remain.

- **`pending_venues.json`** — populated daily by the scout agent (`scout.py`), a web-search
  LLM loop. Each candidate is a place (matches the CSV's shape, `days` included if the scout
  found a schedule). On approval: add the place to the CSV (with a generated `slug`), and if
  it had `days` set, also add a matching event to `chess_scenes_events.json`. Remove from
  the pending file either way.
- **`pending_giant_chessboards.json`** — populated by `giant_chessboard_finder.py` (see
  below). Same review flow; these never have a schedule, so it's CSV-only.
- **`pending_events.json`** — populated by `barblitz_scraper.py` (see below). Each candidate
  is already shaped like a `chess_scenes_events.json` event (place-linked if the scraper
  matched an existing place by name, standalone otherwise). On approval, if it's standalone
  and you can identify/geocode the venue, either fill in its `standalone_lat`/
  `standalone_lng` or — if it turns out to be a place worth having its own pin — add it to
  the CSV and switch the event to reference that `place_slug` instead. Then append it to
  `chess_scenes_events.json`'s `events` list and remove it from the pending file.

---

## Giant chessboard finder

`giant_chessboard_finder.py` sweeps OpenStreetMap's Overpass API for outdoor giant
chessboards in an **explicitly scoped area** (a `sport=chess` tag query plus a
free-text fallback for untagged/mistagged boards), dedupes hits within 50m of each
other, reverse-geocodes each cluster to a city/country via Nominatim, and
cross-checks against the existing CSV to flag likely-already-known places by
proximity (100m). It writes two review files — never auto-publishes, since OSM's
tagging here is noisy (indoor board-game cafes, ordinary playground pitches, etc.
get caught too):

- `giant_chessboards_review.csv` — production CSV columns first (so approved rows
  can be copy-pasted straight into the real CSV — just add a `slug`, e.g. via
  `python3 -c "from app import slugify; print(slugify('Name'))"`; its own `days` column is
  always empty for these, so nothing is lost dropping it), plus `_`-prefixed review metadata
  (OSM link, which query matched, raw tags, possible-duplicate flag).
- `pending_giant_chessboards.json` — same shape as `pending_venues.json` (labels as
  a list) so it can go through the same one-by-one review flow as scout candidates,
  kept in its own file rather than merged into the scout's queue.

**`--area "City Name"` or `--bbox south,west,north,east` is mandatory — there is no
global/unscoped mode.** The first version of this script ran the free-text query
unscoped: a regex scan over the `name`/`description` tag across every named node on
the entire planet. That's a full-text scan, not an indexed tag lookup, against a
free community-funded public API — it had to be manually cancelled mid-run after
burning ~20 minutes retrying an oversized query. `build_queries()` now refuses to
run without exactly one of `area=`/`bbox=`, and the CLI enforces the same via a
required mutually-exclusive group — this fails fast with a usage error, before any
network call. If a genuinely global sweep is ever wanted, that needs its own
deliberate design (e.g. iterating per-country with real pacing between requests,
not a bigger blanket regex) — don't route around the `--area`/`--bbox` requirement
to get back to an unbounded query.

Needs real internet access to `overpass-api.de` and `nominatim.openstreetmap.org`.
Run it locally, or via the manually-triggered **Giant Chessboard Finder** GitHub
Actions workflow (`.github/workflows/giant_chessboard_finder.yml`, same
checkout-and-push pattern as `scout.yml`) — its `workflow_dispatch` inputs
(`area`/`admin_level`/`bbox`, defaulting to Amsterdam) make the scope visible in the
GitHub UI before anyone clicks Run. It will not work from a network-sandboxed
session that blocks those hosts. `test_giant_chessboard_finder.py` covers the
dedupe/clustering/duplicate-flagging/query-scoping logic offline, without hitting
either API.

---

## Barblitz scraper

`barblitz_scraper.py` — a **hand-written HTML parser** (`requests` + `BeautifulSoup`, no
LLM, no per-run cost) for barblitz.co, a roaming Amsterdam-area chess tournament series with
no fixed venue and no API. Its homepage has a stable tournament grid: each upcoming
tournament is a `.tc-card` with a real ISO `<time datetime>`, a title, and a venue/city
line — no date-text parsing or web search needed.

Each scraped tournament's venue name is fuzzy-matched against the places CSV; a match
attaches `place_slug` (e.g. tournaments at Cafe de Laurierboom, which is already a place in
its own right), a non-match becomes a standalone candidate (venue name + city, no
coordinates yet — see review flow above). This is deliberate: Barblitz's other venues
(random bars used once) should never get a permanent pin just because of a traveling event.

**If barblitz.co changes its markup**, the `.tc-card` selectors stop matching and the
script raises (`MIN_EXPECTED_CARDS` guard) rather than silently writing zero candidates.
That fails the GitHub Actions step, and GitHub's default failure-notification email is the
alert that it's time to come update the selectors — or, if barblitz.co ever ships a real
API, switch to that instead of scraping HTML at all.

Runs weekly via `.github/workflows/barblitz_scraper.yml` (also manually triggerable),
writing candidates to `pending_events.json`.

---

## Shareable pages and social previews

Every URL on the site has its own server-rendered `<meta>` tags (Jinja auto-escapes these —
no special escaping needed) so a WhatsApp/social share looks like the actual thing being
shared, not one generic card:

- **`/place/<slug>`** and **`/event/<id>`** — per-item `og:image` uses the place's own photo
  or the community's photo. `/venue/<slug>` (the old path) 301-redirects to `/place/<slug>`
  so links shared before the places/events rename still work.
- **`/city/<slug>`** — renders the same map/sidebar app, pre-filtered to that city. Its
  `og:image` is a **generated static map** (see below), not a stock photo — deliberately,
  since there's no single real photo that represents "a city." `slug` is computed via
  `slugify()` against each city's real name; there's no stored city-slug column,
  `find_city_by_slug()` just scans `SELECT DISTINCT city FROM places` and matches.
  `/api/cities` returns `[{name, slug}, ...]`.
- **`/` (homepage)** — `og:image` is a static map of *every* place globally rather than a
  stock photo, so a bare link share looks like something real and specific ("169 places to
  find chess around the world…") instead of one fixed generic image.

**Static map generation** (`render_pin_map()` in `app.py`, served via `/map.png` and
`/city/<slug>/map.png`): fetches real OpenStreetMap raster tiles (`tile.openstreetmap.org`,
with an identifying `User-Agent` per their usage policy) covering the places' bounding box,
stitches them into a 1200×630 canvas via Pillow, then draws a solid maroon/cream pin
(`MAP_PIN_COLOR`/`MAP_PIN_OUTLINE`, matching `--maroon`/`--cream` in `templates/index.html`)
at each place's projected pixel position using standard Web Mercator tile math
(`_lonlat_to_pixel`/`_fit_zoom`). A single place (or all-identical coordinates) gets padded
by ~0.02° so it doesn't degenerate to a single dot with no context. Results are cached
in-memory (`_map_image_cache`, keyed by city + point count + sorted coordinates so it
self-invalidates when places are added/moved) — safe because this app runs as a single
process (`Procfile`: `python3 app.py`, no gunicorn workers), unlike chess-library-api's
Postgres-backed rate limiter which had to account for multiple workers. Don't add a
persistent/disk cache for this — it's meant to regenerate cheaply on the next deploy, and a
committed PNG per city would go stale silently as places get added.

**On the frontend**, map pins are re-fetched (`refreshMapPins(city, day)` in
`templates/index.html`) on every city/day filter change, not loaded once globally — grey
pins are every place in the selected city (`/api/places?city=`), red pins are whichever of
those (or standalone events) have a matching event for the selected day
(`/api/events?city=&day=`). This is what keeps the map and the scenes list from disagreeing:
they're the same query, filtered the same way.

**Pin color vs. pin glyph are two independent signals.** Color (red/grey,
`pin-active`/`pin-inactive` CSS classes) is purely "does this have a matching event today,"
unrelated to what kind of place it is. The glyph inside — a chess piece — is chosen by
`pieceForLabels()` from the place's own `labels` (or `null` for a standalone/roaming event
with no place, which falls back to a pawn): board → pawn, museum → bishop, memorial → king,
shop → queen, club → rook, bar/meetup → knight. A place can have multiple labels (e.g. "chess
memorial, chess board"); `PIECE_PRIORITY` picks one, ordered roughly rarest/most-literal
first, so a square with actual physical chess tables shows as a board (pawn) even if it's
also described as a memorial. If you add a new label to the vocabulary at the top of this
file, add it to `PIECE_PRIORITY` too, or it'll silently fall back to a pawn.
