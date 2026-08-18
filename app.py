from flask import Flask, render_template, jsonify, request, g, abort, Response, redirect
import sqlite3
import os
import re
import csv
import json
import jwt
import datetime
import math
import io
import urllib.request
from functools import wraps
from PIL import Image, ImageDraw
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')
# Railway terminates TLS in front of this app and forwards plain HTTP, so
# request.url_root/request.scheme would report "http" even though the public site is
# https-only — trust the one reverse proxy's X-Forwarded-Proto so absolute URLs we build
# (og:image, og:url) get the right scheme instead of a redirect-requiring http:// one.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return re.sub(r'-+', '-', text).strip('-')

DATABASE = 'chess.db'
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Chess Scenes (Public) - chess_scenes_venues.csv')
EVENTS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chess_scenes_events.json')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript('''
        CREATE TABLE IF NOT EXISTS places (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            labels TEXT,
            address TEXT,
            city TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            gmaps TEXT,
            link TEXT,
            image TEXT,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS communities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            image TEXT
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            place_id INTEGER REFERENCES places(id),
            standalone_name TEXT,
            standalone_address TEXT,
            standalone_city TEXT,
            standalone_lat REAL,
            standalone_lng REAL,
            standalone_gmaps TEXT,
            community_id INTEGER REFERENCES communities(id),
            title TEXT NOT NULL,
            time TEXT,
            time_end TEXT,
            format_tag TEXT,
            external_link TEXT,
            notes TEXT,
            specific_date DATE,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS event_recurrences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            day TEXT NOT NULL
        );
    ''')
    db.commit()
    db.close()

def seed_places():
    """places is durably sourced from the committed CSV — wipe and reseed on every
    startup, same convention chessscenes has always used for its directory data."""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute('DELETE FROM places')
    db.commit()

    if not os.path.exists(CSV_PATH):
        db.close()
        return

    seen_slugs = set()
    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row['name'].strip()
            slug = row['slug'].strip()
            if not slug:
                raise ValueError(f'Place {name!r} has no slug in the CSV')
            if slug in seen_slugs:
                raise ValueError(f'Duplicate place slug {slug!r} in the CSV')
            seen_slugs.add(slug)

            coords = row['coordinates'].strip()
            if not coords or ',' not in coords:
                raise ValueError(f'Place {name!r} has no coordinates — places require lat/lng')
            lat_str, lng_str = [p.strip() for p in coords.split(',', 1)]

            db.execute(
                '''INSERT INTO places (name, slug, labels, address, city, lat, lng, gmaps, link, image, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (name, slug, row['labels'].strip() or None, None, row['city'].strip(),
                 float(lat_str), float(lng_str), row['gmap'].strip() or None,
                 row['link'].strip() or None, row['image'].strip() or None, row['note'].strip() or None)
            )

    db.commit()
    db.close()

def seed_communities_and_events():
    """communities/events/event_recurrences are durably sourced from the committed
    chess_scenes_events.json — wipe and reseed on every startup, same as seed_places()."""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute('DELETE FROM event_recurrences')
    db.execute('DELETE FROM events')
    db.execute('DELETE FROM communities')
    db.commit()

    if not os.path.exists(EVENTS_JSON_PATH):
        db.close()
        return

    data = json.loads(open(EVENTS_JSON_PATH, encoding='utf-8').read())

    community_ids = {}
    for name, image in data.get('communities', {}).items():
        cur = db.execute('INSERT INTO communities (name, image) VALUES (?, ?)', (name, image))
        community_ids[name] = cur.lastrowid
    db.commit()

    place_ids = {r['slug']: r['id'] for r in db.execute('SELECT id, slug FROM places').fetchall()}

    for ev in data.get('events', []):
        place_slug = ev.get('place_slug')
        place_id = None
        if place_slug:
            place_id = place_ids.get(place_slug)
            if place_id is None:
                raise ValueError(f'Event {ev.get("title")!r} references unknown place slug {place_slug!r}')
        community_id = community_ids.get(ev.get('community')) if ev.get('community') else None

        cur = db.execute('''INSERT INTO events
            (place_id, standalone_name, standalone_address, standalone_city,
             standalone_lat, standalone_lng, standalone_gmaps, community_id,
             title, time, time_end, format_tag, external_link, notes, specific_date, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (place_id, ev.get('standalone_name'), ev.get('standalone_address'), ev.get('standalone_city'),
             ev.get('standalone_lat'), ev.get('standalone_lng'), ev.get('standalone_gmaps'), community_id,
             ev['title'], ev.get('time'), ev.get('time_end'), ev.get('format_tag'),
             ev.get('external_link'), ev.get('notes'), ev.get('specific_date'),
             1 if ev.get('active', True) else 0))
        event_id = cur.lastrowid
        for day in ev.get('days') or []:
            db.execute('INSERT INTO event_recurrences (event_id, day) VALUES (?, ?)', (event_id, day))

    db.commit()
    db.close()

# --- Auth ---

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token missing'}), 401
        try:
            jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    admin_password = os.environ.get('ADMIN_PASSWORD', 'chess')
    if data.get('password') == admin_password:
        token = jwt.encode({
            'admin': True,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
        }, app.config['SECRET_KEY'], algorithm='HS256')
        return jsonify({'token': token})
    return jsonify({'error': 'Wrong password'}), 401

# --- Public API ---

# COALESCE(place_id fields, standalone_* fields) so callers never need to know whether an
# event is tied to a place or roaming (see Barblitz: place_id is null for the bars it uses
# that aren't otherwise chess places, so no permanent pin gets created for them).
EVENT_SELECT = '''
    SELECT e.id, e.title, e.time, e.time_end, e.format_tag, e.external_link, e.notes,
           e.specific_date, e.active,
           c.name as community_name, c.image as community_image,
           p.slug as place_slug, p.labels as place_labels,
           COALESCE(p.name, e.standalone_name) as place_name,
           COALESCE(p.address, e.standalone_address) as place_address,
           COALESCE(p.city, e.standalone_city) as place_city,
           COALESCE(p.lat, e.standalone_lat) as place_lat,
           COALESCE(p.lng, e.standalone_lng) as place_lng,
           COALESCE(p.gmaps, e.standalone_gmaps) as place_gmaps,
           GROUP_CONCAT(r.day, ',') as recurrence_days
    FROM events e
    LEFT JOIN places p ON e.place_id = p.id
    LEFT JOIN communities c ON e.community_id = c.id
    LEFT JOIN event_recurrences r ON r.event_id = e.id
'''

def fetch_events(city=None, day=None, date=None):
    db = get_db()
    query = EVENT_SELECT + ' WHERE e.active = 1'
    params = []
    if city:
        query += ' AND COALESCE(p.city, e.standalone_city) = ?'
        params.append(city)
    if day:
        query += ''' AND (
            e.id IN (SELECT event_id FROM event_recurrences WHERE day = ?)
            OR e.specific_date = ?
        )'''
        params += [day, date or '']
    query += ' GROUP BY e.id ORDER BY e.time ASC'
    rows = db.execute(query, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['recurrence_days'] = d['recurrence_days'].split(',') if d['recurrence_days'] else []
        result.append(d)
    return result

@app.route('/api/events')
def get_events():
    city = request.args.get('city', 'Amsterdam')
    day = request.args.get('day')
    date = request.args.get('date')
    return jsonify(fetch_events(city, day, date))

@app.route('/api/events/all')
def get_all_events():
    city = request.args.get('city', 'Amsterdam')
    days_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    result = {}
    # One-off (specific_date) events don't fit the weekday-template grouping below — that
    # loop calls fetch_events(city, day) with no date, so its internal
    # `e.specific_date = ?` check always compares against '' and never matches a real
    # date, no matter which weekday the event happens to fall on. Surfaced as its own
    # chronological bucket instead, so it isn't just invisible under "any day".
    one_off = [e for e in fetch_events(city) if e['specific_date']]
    if one_off:
        one_off.sort(key=lambda e: e['specific_date'])
        result['Upcoming'] = one_off
    for day in days_order:
        events = fetch_events(city, day)
        if events:
            result[day] = events
    return jsonify(result)

@app.route('/api/places')
def get_places():
    db = get_db()
    city = request.args.get('city')
    if city:
        rows = db.execute('SELECT * FROM places WHERE city = ? ORDER BY name', (city,)).fetchall()
    else:
        rows = db.execute('SELECT * FROM places ORDER BY name').fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/cities')
def get_cities():
    db = get_db()
    rows = db.execute('SELECT DISTINCT city FROM places ORDER BY city').fetchall()
    return jsonify([{'name': r['city'], 'slug': slugify(r['city'])} for r in rows])

@app.route('/api/place/<slug>')
def api_place(slug):
    db = get_db()
    row = db.execute('SELECT * FROM places WHERE slug=?', (slug,)).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    v = dict(row)
    # Aggregate this place's own recurring days across its active events, for card display
    # (activityLine() in the frontend) — the same role venue_directory.days used to play.
    days_rows = db.execute('''
        SELECT DISTINCT r.day FROM event_recurrences r
        JOIN events e ON e.id = r.event_id
        WHERE e.place_id = ? AND e.active = 1
    ''', (row['id'],)).fetchall()
    order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    days = sorted({d['day'] for d in days_rows}, key=lambda d: order.index(d) if d in order else 99)
    v['days'] = ', '.join(days) if days else None
    return jsonify(v)

@app.route('/api/event/<int:event_id>')
def api_event(event_id):
    db = get_db()
    row = db.execute(EVENT_SELECT + ' WHERE e.id = ? GROUP BY e.id', (event_id,)).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    d = dict(row)
    d['recurrence_days'] = d['recurrence_days'].split(',') if d['recurrence_days'] else []
    return jsonify(d)

# --- Admin API ---

@app.route('/api/admin/communities', methods=['GET'])
@token_required
def admin_communities():
    db = get_db()
    rows = db.execute('SELECT * FROM communities ORDER BY name').fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/admin/communities', methods=['POST'])
@token_required
def create_community():
    data = request.json
    db = get_db()
    cur = db.execute('INSERT INTO communities (name, image) VALUES (?, ?)',
                     (data['name'], data.get('image')))
    db.commit()
    return jsonify({'id': cur.lastrowid}), 201

@app.route('/api/admin/communities/<int:id>', methods=['PUT'])
@token_required
def update_community(id):
    data = request.json
    db = get_db()
    db.execute('UPDATE communities SET name=?, image=? WHERE id=?',
               (data['name'], data.get('image'), id))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/communities/<int:id>', methods=['DELETE'])
@token_required
def delete_community(id):
    db = get_db()
    db.execute('DELETE FROM communities WHERE id=?', (id,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/places', methods=['GET'])
@token_required
def admin_places():
    db = get_db()
    rows = db.execute('SELECT * FROM places ORDER BY city, name').fetchall()
    return jsonify([dict(r) for r in rows])

def _unique_slug(db, name, city):
    base = slugify(name)
    slug = base
    if db.execute('SELECT 1 FROM places WHERE slug=?', (slug,)).fetchone():
        slug = base + '-' + slugify(city)
    counter = 2
    while db.execute('SELECT 1 FROM places WHERE slug=?', (slug,)).fetchone():
        slug = base + '-' + str(counter)
        counter += 1
    return slug

@app.route('/api/admin/places', methods=['POST'])
@token_required
def create_place():
    data = request.json
    db = get_db()
    city = data.get('city', 'Amsterdam')
    slug = _unique_slug(db, data['name'], city)
    cur = db.execute(
        'INSERT INTO places (name, slug, address, gmaps, lat, lng, city) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (data['name'], slug, data.get('address'), data.get('gmaps'), data.get('lat'), data.get('lng'), city))
    db.commit()
    return jsonify({'id': cur.lastrowid}), 201

@app.route('/api/admin/places/<int:id>', methods=['PUT'])
@token_required
def update_place(id):
    data = request.json
    db = get_db()
    db.execute('UPDATE places SET name=?, address=?, gmaps=?, lat=?, lng=?, city=? WHERE id=?',
               (data['name'], data.get('address'), data.get('gmaps'), data.get('lat'), data.get('lng'), data.get('city', 'Amsterdam'), id))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/places/<int:id>', methods=['DELETE'])
@token_required
def delete_place(id):
    db = get_db()
    db.execute('DELETE FROM places WHERE id=?', (id,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/events', methods=['GET'])
@token_required
def admin_events():
    db = get_db()
    rows = db.execute(EVENT_SELECT + ' GROUP BY e.id ORDER BY e.time ASC').fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['recurrence_days'] = d['recurrence_days'].split(',') if d['recurrence_days'] else []
        result.append(d)
    return jsonify(result)

@app.route('/api/admin/events', methods=['POST'])
@token_required
def create_event():
    data = request.json
    db = get_db()
    cur = db.execute('''INSERT INTO events
        (community_id, place_id, title, specific_date, time, time_end, format_tag, external_link, notes, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (data.get('community_id'), data.get('place_id'), data['title'],
         data.get('specific_date'), data.get('time'), data.get('time_end'),
         data.get('format_tag'), data.get('external_link'), data.get('notes'),
         data.get('active', 1)))
    event_id = cur.lastrowid
    for day in data.get('recurrence_days', []):
        db.execute('INSERT INTO event_recurrences (event_id, day) VALUES (?, ?)', (event_id, day))
    db.commit()
    return jsonify({'id': event_id}), 201

@app.route('/api/admin/events/<int:id>', methods=['PUT'])
@token_required
def update_event(id):
    data = request.json
    db = get_db()
    db.execute('''UPDATE events SET
        community_id=?, place_id=?, title=?, specific_date=?,
        time=?, time_end=?, format_tag=?, external_link=?, notes=?, active=?
        WHERE id=?''',
        (data.get('community_id'), data.get('place_id'), data['title'],
         data.get('specific_date'), data.get('time'), data.get('time_end'),
         data.get('format_tag'), data.get('external_link'), data.get('notes'),
         data.get('active', 1), id))
    db.execute('DELETE FROM event_recurrences WHERE event_id=?', (id,))
    for day in data.get('recurrence_days', []):
        db.execute('INSERT INTO event_recurrences (event_id, day) VALUES (?, ?)', (id, day))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/events/<int:id>', methods=['DELETE'])
@token_required
def delete_event(id):
    db = get_db()
    db.execute('DELETE FROM event_recurrences WHERE event_id=?', (id,))
    db.execute('DELETE FROM events WHERE id=?', (id,))
    db.commit()
    return jsonify({'ok': True})

# --- Static pin-map images (used as og:image for city and homepage shares) ---

TILE_SIZE = 256
OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
MAP_USER_AGENT = "ChessScenes/1.0 (+https://chessscenes.com)"
MAP_PIN_COLOR = (107, 26, 42)  # matches --maroon in templates/index.html
MAP_PIN_OUTLINE = (245, 230, 224)  # matches --cream

_tile_cache = {}
_map_image_cache = {}


def _lonlat_to_pixel(lon, lat, zoom):
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n * TILE_SIZE
    y = (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n * TILE_SIZE
    return x, y


def _fit_zoom(min_lon, min_lat, max_lon, max_lat, width, height, max_zoom=15, padding=60):
    for zoom in range(max_zoom, 1, -1):
        x0, y0 = _lonlat_to_pixel(min_lon, max_lat, zoom)
        x1, y1 = _lonlat_to_pixel(max_lon, min_lat, zoom)
        if (x1 - x0) <= (width - padding * 2) and (y1 - y0) <= (height - padding * 2):
            return zoom
    return 2


def _fetch_tile(z, x, y):
    n = 2 ** z
    x = x % n
    if y < 0 or y >= n:
        return None
    key = (z, x, y)
    if key in _tile_cache:
        return _tile_cache[key]
    req = urllib.request.Request(OSM_TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": MAP_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        img = None
    _tile_cache[key] = img
    return img


def render_pin_map(points, width=1200, height=630):
    """points: list of (lat, lng). Returns PNG bytes of a static OSM map with pins, or None if no points."""
    if not points:
        return None
    lats = [p[0] for p in points]
    lngs = [p[1] for p in points]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)
    if min_lat == max_lat and min_lng == max_lng:
        pad = 0.02
        min_lat -= pad
        max_lat += pad
        min_lng -= pad
        max_lng += pad

    zoom = _fit_zoom(min_lng, min_lat, max_lng, max_lat, width, height)
    center_lng = (min_lng + max_lng) / 2
    center_lat = (min_lat + max_lat) / 2
    center_x, center_y = _lonlat_to_pixel(center_lng, center_lat, zoom)
    left = center_x - width / 2
    top = center_y - height / 2

    canvas = Image.new("RGB", (width, height), (232, 208, 200))  # --cream-dark fallback
    first_tx, first_ty = int(left // TILE_SIZE), int(top // TILE_SIZE)
    last_tx, last_ty = int((left + width) // TILE_SIZE), int((top + height) // TILE_SIZE)
    for tx in range(first_tx, last_tx + 1):
        for ty in range(first_ty, last_ty + 1):
            tile = _fetch_tile(zoom, tx, ty)
            if tile is None:
                continue
            canvas.paste(tile, (int(tx * TILE_SIZE - left), int(ty * TILE_SIZE - top)))

    draw = ImageDraw.Draw(canvas)
    for lat, lng in points:
        px, py = _lonlat_to_pixel(lng, lat, zoom)
        x, y = px - left, py - top
        if -20 <= x <= width + 20 and -20 <= y <= height + 20:
            r = 7
            draw.ellipse([x - r, y - r, x + r, y + r], fill=MAP_PIN_COLOR, outline=MAP_PIN_OUTLINE, width=2)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def get_points(city=None):
    """Every place's coordinates for a city (or globally if city is None)."""
    db = get_db()
    if city:
        rows = db.execute(
            'SELECT lat, lng FROM places WHERE city = ?', (city,)).fetchall()
    else:
        rows = db.execute('SELECT lat, lng FROM places').fetchall()
    return [(r['lat'], r['lng']) for r in rows]


def find_city_by_slug(slug):
    db = get_db()
    rows = db.execute('SELECT DISTINCT city FROM places').fetchall()
    for r in rows:
        if slugify(r['city']) == slug:
            return r['city']
    return None


@app.route('/map.png')
def global_map_image():
    points = get_points()
    cache_key = ('__global__', len(points), tuple(sorted(points)))
    if cache_key not in _map_image_cache:
        png = render_pin_map(points)
        if not png:
            abort(404)
        _map_image_cache[cache_key] = png
    return Response(_map_image_cache[cache_key], mimetype='image/png')


@app.route('/city/<slug>/map.png')
def city_map_image(slug):
    city = find_city_by_slug(slug)
    if not city:
        abort(404)
    points = get_points(city)
    if not points:
        abort(404)
    cache_key = (city, len(points), tuple(sorted(points)))
    if cache_key not in _map_image_cache:
        png = render_pin_map(points)
        if not png:
            abort(404)
        _map_image_cache[cache_key] = png
    return Response(_map_image_cache[cache_key], mimetype='image/png')


# --- Pages ---

@app.route('/')
def index():
    points = get_points()
    count = len(points)
    return render_template('index.html',
        og_title="Chess Scenes",
        og_description=f"{count} places to find chess around the world — clubs, bars, outdoor boards, museums, memorials." if count else None,
        og_image=(request.url_root.rstrip('/') + '/map.png') if count else None,
        og_url="/",
    )

@app.route('/city/<slug>')
def city_page(slug):
    city = find_city_by_slug(slug)
    if not city:
        abort(404)
    points = get_points(city)
    count = len(points)
    desc = f"{count} chess spot{'s' if count != 1 else ''} to find in {city}." if count else f"Chess spots in {city}."
    return render_template('index.html',
        og_title=f"Chess in {city} · Chess Scenes",
        og_description=desc,
        og_image=(request.url_root.rstrip('/') + f'/city/{slug}/map.png') if count else None,
        og_url=f"/city/{slug}",
    )

@app.route('/venue/<slug>')
def venue_redirect(slug):
    return redirect(f'/place/{slug}', code=301)

@app.route('/place/<slug>')
def place_page(slug):
    db = get_db()
    row = db.execute('SELECT * FROM places WHERE slug=?', (slug,)).fetchone()
    if not row:
        abort(404)
    v = dict(row)
    name = v.get('name', '')
    city = v.get('city', '')
    days_rows = db.execute('''
        SELECT DISTINCT r.day FROM event_recurrences r
        JOIN events e ON e.id = r.event_id
        WHERE e.place_id = ? AND e.active = 1
    ''', (row['id'],)).fetchall()
    desc_parts = [f"Chess venue in {city}"]
    if days_rows:
        order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
        days = sorted({d['day'] for d in days_rows}, key=lambda d: order.index(d) if d in order else 99)
        desc_parts.append(f"Active on {', '.join(days)}")
    if v.get('note'):
        desc_parts.append(v['note'])
    return render_template('index.html',
        og_title=f"{name} · Chess Scenes",
        og_description=" · ".join(desc_parts),
        og_image=v.get('image'),
        og_url=f"/place/{slug}",
    )

@app.route('/event/<int:event_id>')
def event_page(event_id):
    db = get_db()
    row = db.execute(EVENT_SELECT + ' WHERE e.id = ? GROUP BY e.id', (event_id,)).fetchone()
    if not row:
        abort(404)
    ev = dict(row)
    city = ev.get('place_city', '')
    name = ev.get('title', '')
    place = ev.get('place_name', '')
    desc_parts = [f"Chess in {city}"]
    if place:
        desc_parts.append(f"at {place}")
    if ev.get('notes'):
        desc_parts.append(ev['notes'])
    return render_template('index.html',
        og_title=f"{name} · Chess Scenes",
        og_description=" · ".join(desc_parts),
        og_image=ev.get('community_image'),
        og_url=f"/event/{event_id}",
    )

@app.route('/admin')
def admin():
    return render_template('admin.html')

if __name__ == '__main__':
    init_db()
    seed_places()
    seed_communities_and_events()
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=False, host='0.0.0.0', port=port)
