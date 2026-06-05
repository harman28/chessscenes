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

---

## Adding new venues or events (mobile screenshot workflow)

Harman may send a screenshot of a chess venue or event listing (from Instagram, Google Maps, a website, etc.) and ask you to add it. When this happens:

1. **Extract from the screenshot**: name, city, labels (pick from the list above), coordinates (lat/lng — look them up via the note/address if not visible), note (brief description of what it is / when it meets), Google Maps link, website/Instagram link, image URL (imgur preferred — ask Harman if none available), days (comma-separated day names if it recurs on specific days, e.g. `Tuesday` or `Friday, Saturday`).

2. **Add a row to the CSV** at `/Users/harmansingh/workplace/chess scenes project/chessscenes/Chess Scenes (Public) - chess_scenes_venues.csv`. Column order: `name,labels,city,coordinates,note,gmap,link,image,days,id`. Leave `id` empty. Quote the coordinates field: `"lat, lng"`. Quote the days field if multiple: `"Monday, Wednesday"`.

3. **Commit and push**:
   ```
   git add "Chess Scenes (Public) - chess_scenes_venues.csv"
   git commit -m "Add <name> (<city>)"
   git push origin main
   ```

Railway auto-deploys on push. `seed_directory()` runs on startup and reseeds `venue_directory` from the CSV. The new entry will appear on the map within ~30 seconds.

**Principle**: the site tells you where to go to find chess. This includes clubs, bars (with days they have chess), outdoor boards, museums, shops, memorials. If something has `days` set, it shows up in the events sidebar as well as on the map.
