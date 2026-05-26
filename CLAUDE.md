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
