# Chess Scenes — Project Guide for Claude Code

## What this is
A full-stack web app for discovering real-world chess venues and events globally.
- **Backend**: Python + Flask + SQLAlchemy ORM + SQLite
- **Frontend**: Vanilla HTML/CSS/JS, multi-file, served separately (or via Flask in prod)
- **Auth**: JWT (HS256) for admin routes only

## Project structure
```
chessscenes/
├── CLAUDE.md
├── backend/
│   ├── app.py              # Flask app factory
│   ├── config.py
│   ├── extensions.py       # SQLAlchemy instance (avoid circular imports)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── place.py        # Place model
│   │   ├── event.py        # Event model
│   │   ├── suggestion.py   # Suggestion model
│   │   ├── user.py         # Admin user model
│   │   └── setting.py      # Key/value site settings
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py         # POST /api/auth/login, /create-admin
│   │   ├── places.py       # Public place routes
│   │   ├── events.py       # Public event routes
│   │   ├── suggestions.py  # Public suggestion submission
│   │   └── admin.py        # Protected CRUD + approval + settings
│   ├── auth.py             # JWT helpers + require_auth decorator
│   ├── migrate.py          # CSV → DB import script
│   └── requirements.txt
└── frontend/
    ├── index.html          # Map view (Leaflet, clustered pins)
    ├── find.html           # "Find chess" — city + date picker → results
    ├── admin.html          # Admin dashboard: places, suggestions, events, settings
    ├── css/
    │   └── main.css
    └── js/
        ├── api.js          # Fetch wrapper, token storage, base URL config
        ├── map.js          # Leaflet map init, pin rendering, clustering
        ├── find.js         # Find chess flow
        └── admin.js        # Admin dashboard logic incl. LLM-assisted entry
```

## Key conventions
- All API routes are prefixed `/api/`
- Admin routes are prefixed `/api/admin/` and require `Authorization: Bearer <token>`
- SQLAlchemy models live in `backend/models/`, imported via `backend/models/__init__.py`
- `extensions.py` holds the `db = SQLAlchemy()` instance to avoid circular imports
- Frontend `api.js` exports a base URL constant — change this for prod deployment

## Data model summary

### Place
Core entity. Fields: id, name, slug, city, country, lat, lng, type, description,
schedule_notes, schedule_days (comma-sep e.g. "mon,wed"), website, image_url,
verified (bool), active (bool), created_at, updated_at.

Place types: chess_board, chess_shop, chess_bar, chess_club, chess_meetup,
chess_memorial, chess_museum

### Event
A specific dated occurrence. Can be linked to a Place (place_id nullable).
Fields: id, place_id, name, city, country, lat, lng, event_date (ISO string),
event_time (HH:MM), description, url, created_at.

### Suggestion
Public submissions. Status: pending → approved (becomes a Place, verified=False) or rejected.
Fields mirror Place plus submitter_name, submitter_email, admin_notes.

### Setting
Key/value store. Current keys:
- `show_unverified`: "true"/"false" — global toggle, respected by all public endpoints

### User
Admin only. Fields: id, username, password_hash, created_at.
Bootstrap via POST /api/auth/create-admin (only works when no users exist).

## Auth flow
1. POST /api/auth/login → returns JWT token
2. Store token in localStorage (admin.js handles this)
3. All /api/admin/* requests include `Authorization: Bearer <token>`

## LLM-assisted data entry (admin)
admin.js includes a tool where you paste text or upload a screenshot of a chess
club page. It calls the Anthropic API (claude-sonnet-4-20250514) with the content
and a structured prompt to extract: name, city, country, lat/lng (via geocoding
hint), type, description, schedule_notes, schedule_days, website.
The result pre-fills the "Add Place" form for review before saving.

## Local dev
```bash
cd backend
pip3 install -r requirements.txt
# First time only:
curl -X POST http://localhost:5000/api/auth/create-admin \
  -H "Content-Type: application/json" \
  -d '{"username": "harman", "password": "yourpassword"}'
python3 app.py
# Frontend: open frontend/index.html directly or:
cd ../frontend && python3 -m http.server 8080
```

## CSV migration
```bash
cd backend
python3 migrate.py --csv path/to/your.csv
```
Column names are flexible — see COLUMN_MAP in migrate.py for aliases.

## Moving to production
- Set SECRET_KEY env var (never use the default)
- Switch DATABASE path to a persistent volume
- Serve frontend via Flask static files or a CDN
- Consider adding rate limiting to /api/suggestions
