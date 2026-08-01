from flask import Flask, render_template, jsonify, request, g, abort, Response
import sqlite3
import os
import re
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
        CREATE TABLE IF NOT EXISTS communities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            image TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS venues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT,
            gmaps TEXT,
            lat REAL,
            lng REAL,
            city TEXT NOT NULL DEFAULT 'Amsterdam',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            community_id INTEGER REFERENCES communities(id),
            venue_id INTEGER REFERENCES venues(id),
            title TEXT NOT NULL,
            specific_date DATE,
            time TEXT,
            time_end TEXT,
            format_tag TEXT,
            external_link TEXT,
            notes TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS venue_directory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            labels TEXT,
            address TEXT,
            city TEXT NOT NULL DEFAULT 'Amsterdam',
            lat REAL,
            lng REAL,
            gmaps TEXT,
            link TEXT,
            image TEXT,
            note TEXT,
            days TEXT
        );

        CREATE TABLE IF NOT EXISTS event_recurrences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            day TEXT NOT NULL
        );
    ''')
    db.commit()
    # Migrations
    try:
        db.execute('ALTER TABLE venue_directory ADD COLUMN days TEXT')
        db.commit()
    except Exception:
        pass
    try:
        db.execute('ALTER TABLE venue_directory ADD COLUMN slug TEXT')
        db.commit()
    except Exception:
        pass
    db.close()

def seed_directory():
    import csv as csv_module
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute('DELETE FROM venue_directory')
    db.commit()

    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Chess Scenes (Public) - chess_scenes_venues.csv')
    if not os.path.exists(csv_path):
        db.close()
        return

    seen_slugs = set()
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv_module.DictReader(f)
        for row in reader:
            name   = row['name'].strip()
            labels = row['labels'].strip() or None
            city   = row['city'].strip()
            note   = row['note'].strip() or None
            gmaps  = row['gmap'].strip() or None
            link   = row['link'].strip() or None
            image  = row['image'].strip() or None
            days   = row['days'].strip() or None
            lat, lng = None, None
            coords = row['coordinates'].strip()
            if coords:
                parts = coords.split(',')
                if len(parts) == 2:
                    try:
                        lat = float(parts[0].strip())
                        lng = float(parts[1].strip())
                    except ValueError:
                        pass
            base = slugify(name)
            slug = base
            if slug in seen_slugs:
                slug = base + '-' + slugify(city)
            counter = 2
            while slug in seen_slugs:
                slug = base + '-' + str(counter)
                counter += 1
            seen_slugs.add(slug)
            db.execute(
                'INSERT INTO venue_directory (name, labels, address, city, lat, lng, gmaps, link, image, note, days, slug) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (name, labels, None, city, lat, lng, gmaps, link, image, note, days, slug)
            )

    db.commit()
    db.close()

def seed_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    # Clear all seeded data to force clean reseed
    db.execute('DELETE FROM event_recurrences')
    db.execute('DELETE FROM events')
    db.execute('DELETE FROM venues')
    db.execute('DELETE FROM communities')
    db.execute("DELETE FROM sqlite_sequence WHERE name IN ('communities','venues','events','event_recurrences')")
    db.commit()

    communities = [
        ('Zwart op Wit',                  'https://i.imgur.com/8jibVQ6.jpeg'),
        ('Schaakvereniging Amsterdam West','https://i.imgur.com/inhlo0q.jpeg'),
        ('Schaakvereniging Caissa',        'https://i.imgur.com/S7Sk0IW.jpeg'),
        ('Pegasus Amstelveen',             'https://i.imgur.com/RHugkLY.jpeg'),
        ('Schaakvereniging EsPion',        'https://i.imgur.com/nlSMpwC.jpeg'),
        ('De Queer Schaakclub',            'https://i.imgur.com/G6UwvNd.jpeg'),
        ('De Volewijckers',                None),
        ('Max Euwe Centrum',               'https://i.imgur.com/inTkxpx.jpeg'),
        ('Chess & Beer',                   'https://i.imgur.com/RTWaMou.png'),
        ('Vondelbunker Chess',             'https://i.imgur.com/zgYqQLp.png'),
        ('Amsterdam Spirit Chess Club',    'https://i.imgur.com/qrvUv5i.png'),
        ('Barblitz Amsterdam',             'https://i.imgur.com/9NRex3f.jpeg'),
        ('Cafe de Laurierboom',            'https://i.imgur.com/9NRex3f.jpeg'),
        ('Schaakcafe Utrecht',             'https://i.imgur.com/wlhqWob.jpeg'),
        ('Stichting En Passant',           'https://i.imgur.com/fVrdQDp.jpeg'),
        ('KopieKoffie',                    'https://i.imgur.com/pC1qmvK.jpeg'),
    ]
    for name, image in communities:
        db.execute('INSERT INTO communities (name, image) VALUES (?, ?)', (name, image))

    venues = [
        ('2 Klaveren',          'Rozengracht 2',              'https://maps.app.goo.gl/2iYpS9ALfHsJLAwYA', 52.3711, 4.8662, 'Amsterdam'),
        ('Bilderdijkpark',      'Bilderdijkpark, Amsterdam',  'https://maps.app.goo.gl/HE7btnNk4Bit5ywy8', 52.3718, 4.8688, 'Amsterdam'),
        ('Huize Lydia',         'Churchilllaan 223',          'https://maps.app.goo.gl/cnJ446iJsELTRz7XA', 52.3532, 4.8833, 'Amsterdam'),
        ('La Plaza, Groenelaan','Groenelaan, Amstelveen',     'https://maps.app.goo.gl/3msMbTPckGVqGh9d9', 52.2926, 4.8745, 'Amsterdam'),
        ('Gaaspstraat 8',       'Gaaspstraat 8, Amsterdam',   'https://maps.app.goo.gl/dZG9V7rcx1a9q3rLA', 52.3452, 4.9085, 'Amsterdam'),
        ('Speelzaal KLUP',      'Speelzaal KLUP, Amsterdam',  'https://maps.app.goo.gl/4hLHEWU5ktfCiWCXA', 52.3544, 4.8545, 'Amsterdam'),
        ('Het Zwanenmeer',      'Het Zwanenmeer, Amsterdam',  'https://maps.app.goo.gl/mqUyi83fLoGxKCwi8', 52.3956, 4.9499, 'Amsterdam'),
        ('Max Euwe Centrum',    'Max Euweplein 30a',          'https://maps.app.goo.gl/5GeJKV1nBEopb1M29', 52.3628, 4.8828, 'Amsterdam'),
        ('Cafe De Balie',       'Kleine-Gartmanplantsoen 10', 'https://maps.app.goo.gl/bkpboKbMJeadL65F6', 52.3632, 4.8830, 'Amsterdam'),
        ('Vondelbunker',        'Vondelpark, Amsterdam',      'https://maps.app.goo.gl/zVaGJ4eQ19HZ6h6z8', 52.3609, 4.8776, 'Amsterdam'),
        ('KLABU Clubhouse',     'Haarlemmerdijk 106',         'https://maps.app.goo.gl/Hwt9yytsy1LJbFCa8', 52.3831, 4.8865, 'Amsterdam'),
        ('Cafe de Laurierboom', 'Laurierstraat 39',           'https://maps.app.goo.gl/PizEC9TRQ4kt8QyK6', 52.3723, 4.8809, 'Amsterdam'),
        ('Schaakcafe Utrecht',  'Oudegracht 321, Utrecht',    'https://maps.app.goo.gl/j7A7ARS1a3TkKk6',   52.09976268371182, 5.103186467326744, 'Utrecht'),
        ('Stichting En Passant','Den Haag',                   'https://maps.app.goo.gl/2A2fRFpQfjugkGRg9', 52.07432068089482, 4.311602878673388, 'The Hague'),
        ('KopieKoffie',         'Oude Delft, Delft',          'https://maps.app.goo.gl/zz2rpLMpYdpqykU98', 52.00047872546669, 4.3460540624039785,'Delft'),
    ]
    for name, address, gmaps, lat, lng, city in venues:
        db.execute('INSERT INTO venues (name, address, gmaps, lat, lng, city) VALUES (?, ?, ?, ?, ?, ?)', (name, address, gmaps, lat, lng, city))

    def cid(name):
        return db.execute('SELECT id FROM communities WHERE name=?', (name,)).fetchone()[0]

    def vid(name):
        return db.execute('SELECT id FROM venues WHERE name=?', (name,)).fetchone()[0]

    ALL_DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']

    events = [
        # (community_name, venue_name, title, specific_date, time, time_end, format_tag, external_link, notes, days)
        ('Zwart op Wit',                  '2 Klaveren',          'Zwart op Wit Club Night',       None, '20:00', None,    'Club night', 'https://www.zwartopwit.org/',                         None,                        ['Monday']),
        ('Schaakvereniging EsPion',        'Gaaspstraat 8',       'EsPion Club Night',              None, '20:00', None,    'Club night', 'https://www.espion.nl/',                              None,                        ['Monday']),
        ('Schaakvereniging Caissa',        'Huize Lydia',         'Caissa Club Night',              None, '20:00', None,    'Club night', 'http://www.caissa-amsterdam.nl/',                     None,                        ['Tuesday']),
        ('Pegasus Amstelveen',             'La Plaza, Groenelaan','Pegasus Club Night',             None, '19:45', None,    'Club night', 'https://www.pegasusamstelveen.nl',                    None,                        ['Tuesday']),
        ('De Queer Schaakclub',            'Speelzaal KLUP',      'De Queer Schaakclub',            None, '20:00', None,    'Club night', 'https://dequeerschaakclub.nl/',                       None,                        ['Wednesday']),
        ('De Volewijckers',                'Het Zwanenmeer',      'De Volewijckers Club Night',     None, '20:00', None,    'Club night', 'https://www.schaakverenigingdevolewijckers.nl/',      None,                        ['Wednesday']),
        ('Schaakvereniging Amsterdam West','Bilderdijkpark',      'Amsterdam West Club Night',      None, '20:00', None,    'Club night', 'https://www.svamsterdamwest.nl/',                     None,                        ['Thursday']),
        ('Max Euwe Centrum',               'Max Euwe Centrum',    'Max Euwe Centrum Open Hours',    None, '10:00', '16:00', 'Open play',  'https://maxeuwe.nl/',                                'Open Tue–Sat',              ['Tuesday','Wednesday','Thursday','Friday','Saturday']),
        ('Chess & Beer',                   'Cafe De Balie',       'Chess & Beer',                   None, '14:00', None,    'Casual',     'https://www.meetup.com/amsterdam-chess-and-beer/',   'Every second Sunday',       ['Sunday']),
        ('Vondelbunker Chess',             'Vondelbunker',        'Vondelbunker Chess',             None, '14:00', None,    'Casual',     'https://radar.squat.net/en/event/amsterdam/vondelbunker/2026-05-17/bunker-chess-club', 'Irregular — check link', ['Sunday']),
        ('Amsterdam Spirit Chess Club',    'KLABU Clubhouse',     'Amsterdam Spirit Chess Club',    None, '15:00', '18:00', 'Casual',     'https://klabu.org/clubhouses/amsterdam',              None,                        ['Sunday']),
        ('Barblitz Amsterdam',             'Cafe de Laurierboom', 'Barblitz Amsterdam',             None,  None,   None,    'Blitz',      'https://barblitz.co',                                'Scraper needed — check barblitz.co for upcoming dates', []),
        ('Cafe de Laurierboom',            'Cafe de Laurierboom', 'Cafe de Laurierboom',            None, '15:00', None,    'Casual',     'https://maps.app.goo.gl/PizEC9TRQ4kt8QyK6',          'Hours vary: Wed–Thu until 01:00, Fri–Sat until 03:00, Sun–Tue until 01:00', ALL_DAYS),
        ('Schaakcafe Utrecht',             'Schaakcafe Utrecht',  'Schaakcafe Utrecht',             None, '13:30', '17:00', 'Casual',     'https://www.schakeninutrecht.nl/schaakcafe/',         None,                        ['Friday']),
        ('Stichting En Passant',           'Stichting En Passant','Stichting En Passant',           None, '14:00', None,    'Club night', 'https://www.stichtingenpassant.nl/',                  'Chess on weekends.',        ['Friday','Saturday','Sunday']),
        ('KopieKoffie',                    'KopieKoffie',         'KopieKoffie Chess',              None, '15:30', None,    'Casual',     'https://kopiekoffie.nl/blog/events/schaken-bij-kopiekoffie/', None,              ['Sunday']),
    ]
    for community_name, venue_name, title, specific_date, time, time_end, format_tag, external_link, notes, days in events:
        cur = db.execute('''INSERT INTO events
            (community_id, venue_id, title, specific_date, time, time_end, format_tag, external_link, notes, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)''',
            (cid(community_name), vid(venue_name), title, specific_date, time, time_end, format_tag, external_link, notes))
        event_id = cur.lastrowid
        for day in days:
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

def fetch_events(city=None, day=None, date=None):
    db = get_db()
    base = '''
        SELECT DISTINCT e.id, e.title, e.specific_date, e.time,
               e.time_end, e.format_tag, e.external_link, e.notes,
               c.name as community_name, c.image as community_image,
               v.name as venue_name, v.address as venue_address, v.gmaps as venue_gmaps, v.lat as venue_lat, v.lng as venue_lng,
               GROUP_CONCAT(r.day, ',') as recurrence_days
        FROM events e
        LEFT JOIN communities c ON e.community_id = c.id
        LEFT JOIN venues v ON e.venue_id = v.id
        LEFT JOIN event_recurrences r ON r.event_id = e.id
        WHERE e.active = 1
    '''
    params = []
    if city:
        base += ' AND v.city = ?'
        params.append(city)
    if day:
        base += ''' AND (
            e.id IN (SELECT event_id FROM event_recurrences WHERE day = ?)
            OR e.specific_date = ?
        )'''
        params += [day, date or '']
    base += ' GROUP BY e.id ORDER BY e.time ASC'
    rows = db.execute(base, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['recurrence_days'] = d['recurrence_days'].split(',') if d['recurrence_days'] else []
        result.append(d)

    # Also surface venue_directory entries that have days set, as event-like rows.
    # Offset id to avoid collision with events.id (autoincrement, unlikely to reach 1M).
    vd_query = '''
        SELECT id + 1000000 as id, name as title, NULL as specific_date, NULL as time,
               NULL as time_end, NULL as format_tag, link as external_link, note as notes,
               NULL as community_name, image as community_image,
               name as venue_name, address as venue_address, gmaps as venue_gmaps,
               lat as venue_lat, lng as venue_lng,
               days as recurrence_days, slug as venue_slug
        FROM venue_directory
        WHERE days IS NOT NULL AND days != ''
    '''
    vd_params = []
    if city:
        vd_query += ' AND city = ? AND name NOT IN (SELECT name FROM venues WHERE city = ?)'
        vd_params += [city, city]
    else:
        vd_query += ' AND name NOT IN (SELECT name FROM venues)'
    if day:
        vd_query += ' AND days LIKE ?'
        vd_params.append(f'%{day}%')
    for r in db.execute(vd_query, vd_params).fetchall():
        d = dict(r)
        d['recurrence_days'] = [x.strip() for x in (d['recurrence_days'] or '').split(',') if x.strip()]
        result.append(d)

    return result

@app.route('/api/events')
def get_events():
    city = request.args.get('city', 'Amsterdam')
    day = request.args.get('day')
    date = request.args.get('date')
    return jsonify(fetch_events(city, day, date))

@app.route('/api/events/global')
def get_global_events():
    """All events worldwide with coords — used for map pins."""
    return jsonify(fetch_events())

@app.route('/api/events/all')
def get_all_events():
    city = request.args.get('city', 'Amsterdam')
    days_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    result = {}
    for day in days_order:
        events = fetch_events(city, day)
        if events:
            result[day] = events
    return jsonify(result)

@app.route('/api/cities')
def get_cities():
    db = get_db()
    rows = db.execute('SELECT DISTINCT city FROM venue_directory ORDER BY city').fetchall()
    return jsonify([{'name': r['city'], 'slug': slugify(r['city'])} for r in rows])

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

@app.route('/api/admin/venues', methods=['GET'])
@token_required
def admin_venues():
    db = get_db()
    rows = db.execute('SELECT * FROM venues ORDER BY city, name').fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/admin/venues', methods=['POST'])
@token_required
def create_venue():
    data = request.json
    db = get_db()
    cur = db.execute('INSERT INTO venues (name, address, gmaps, lat, lng, city) VALUES (?, ?, ?, ?, ?, ?)',
                     (data['name'], data.get('address'), data.get('gmaps'), data.get('lat'), data.get('lng'), data.get('city', 'Amsterdam')))
    db.commit()
    return jsonify({'id': cur.lastrowid}), 201

@app.route('/api/admin/venues/<int:id>', methods=['PUT'])
@token_required
def update_venue(id):
    data = request.json
    db = get_db()
    db.execute('UPDATE venues SET name=?, address=?, gmaps=?, lat=?, lng=?, city=? WHERE id=?',
               (data['name'], data.get('address'), data.get('gmaps'), data.get('lat'), data.get('lng'), data.get('city', 'Amsterdam'), id))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/venues/<int:id>', methods=['DELETE'])
@token_required
def delete_venue(id):
    db = get_db()
    db.execute('DELETE FROM venues WHERE id=?', (id,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/admin/events', methods=['GET'])
@token_required
def admin_events():
    db = get_db()
    rows = db.execute('''
        SELECT e.*, c.name as community_name, v.name as venue_name,
               GROUP_CONCAT(r.day, ',') as recurrence_days
        FROM events e
        LEFT JOIN communities c ON e.community_id = c.id
        LEFT JOIN venues v ON e.venue_id = v.id
        LEFT JOIN event_recurrences r ON r.event_id = e.id
        GROUP BY e.id
        ORDER BY e.time ASC
    ''').fetchall()
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
        (community_id, venue_id, title, specific_date, time, time_end, format_tag, external_link, notes, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (data.get('community_id'), data.get('venue_id'), data['title'],
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
        community_id=?, venue_id=?, title=?, specific_date=?,
        time=?, time_end=?, format_tag=?, external_link=?, notes=?, active=?
        WHERE id=?''',
        (data.get('community_id'), data.get('venue_id'), data['title'],
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

@app.route('/api/venue-directory')
def venue_directory():
    # A venue can legitimately exist in both venue_directory (the general CSV-sourced
    # list) and venues (scheduled-event venues, admin-curated) — excluded here by name so
    # it doesn't render as two separate map pins. Matching by name alone missed
    # near-miss variants (e.g. "Vondelbunker Chess" vs "Vondelbunker" — same place, same
    # gmaps link, different pin) — also matching on gmaps link catches that whole class of
    # duplicate without needing exact name agreement.
    city = request.args.get('city')
    db = get_db()
    if city:
        rows = db.execute('''
            SELECT vd.* FROM venue_directory vd
            WHERE vd.city = ?
            AND vd.lat IS NOT NULL AND vd.lng IS NOT NULL
            AND vd.name NOT IN (SELECT name FROM venues WHERE city = ?)
            AND (vd.gmaps IS NULL OR vd.gmaps = '' OR vd.gmaps NOT IN (
                SELECT gmaps FROM venues WHERE city = ? AND gmaps IS NOT NULL AND gmaps != ''
            ))
            AND (vd.days IS NULL OR vd.days = '')
        ''', (city, city, city)).fetchall()
    else:
        # All venues globally — used for map pins
        rows = db.execute('''
            SELECT vd.* FROM venue_directory vd
            WHERE vd.lat IS NOT NULL AND vd.lng IS NOT NULL
            AND vd.name NOT IN (SELECT name FROM venues)
            AND (vd.gmaps IS NULL OR vd.gmaps = '' OR vd.gmaps NOT IN (
                SELECT gmaps FROM venues WHERE gmaps IS NOT NULL AND gmaps != ''
            ))
            AND (vd.days IS NULL OR vd.days = '')
        ''').fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/venue/<slug>')
def api_venue(slug):
    db = get_db()
    row = db.execute('SELECT * FROM venue_directory WHERE slug=?', (slug,)).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    v = dict(row)
    v['event_id'] = v['id'] + 1000000
    return jsonify(v)

@app.route('/api/event/<int:event_id>')
def api_event(event_id):
    db = get_db()
    row = db.execute('''
        SELECT e.*, c.name as community_name, c.image as community_image,
               v.name as venue_name, v.address as venue_address,
               v.gmaps as venue_gmaps, v.lat as venue_lat, v.lng as venue_lng,
               v.city as city,
               GROUP_CONCAT(r.day, ',') as recurrence_days
        FROM events e
        LEFT JOIN communities c ON e.community_id = c.id
        LEFT JOIN venues v ON e.venue_id = v.id
        LEFT JOIN event_recurrences r ON r.event_id = e.id
        WHERE e.id = ?
        GROUP BY e.id
    ''', (event_id,)).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    d = dict(row)
    d['recurrence_days'] = d['recurrence_days'].split(',') if d['recurrence_days'] else []
    return jsonify(d)

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
    """Every venue's coordinates for a city (or globally if city is None), deduped
    across venue_directory and venues (a venue with scheduled events lives in both)."""
    db = get_db()
    if city:
        rows_a = db.execute(
            'SELECT lat, lng FROM venue_directory WHERE city = ? AND lat IS NOT NULL AND lng IS NOT NULL',
            (city,)).fetchall()
        rows_b = db.execute(
            'SELECT lat, lng FROM venues WHERE city = ? AND lat IS NOT NULL AND lng IS NOT NULL',
            (city,)).fetchall()
    else:
        rows_a = db.execute(
            'SELECT lat, lng FROM venue_directory WHERE lat IS NOT NULL AND lng IS NOT NULL').fetchall()
        rows_b = db.execute(
            'SELECT lat, lng FROM venues WHERE lat IS NOT NULL AND lng IS NOT NULL').fetchall()
    seen = set()
    points = []
    for r in list(rows_a) + list(rows_b):
        key = (round(r['lat'], 5), round(r['lng'], 5))
        if key in seen:
            continue
        seen.add(key)
        points.append((r['lat'], r['lng']))
    return points


def find_city_by_slug(slug):
    db = get_db()
    rows = db.execute('SELECT DISTINCT city FROM venue_directory').fetchall()
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
        initial_data={
            'type': 'city',
            'city': city,
            'slug': slug,
        }
    )

@app.route('/venue/<slug>')
def venue_page(slug):
    db = get_db()
    row = db.execute('SELECT * FROM venue_directory WHERE slug=?', (slug,)).fetchone()
    if not row:
        abort(404)
    v = dict(row)
    name = v.get('name', '')
    city = v.get('city', '')
    desc_parts = [f"Chess venue in {city}"]
    if v.get('days'):
        desc_parts.append(f"Active on {v['days']}")
    if v.get('note'):
        desc_parts.append(v['note'])
    return render_template('index.html',
        og_title=f"{name} · Chess Scenes",
        og_description=" · ".join(desc_parts),
        og_image=v.get('image'),
        og_url=f"/venue/{slug}",
        initial_data={
            'type': 'venue',
            'slug': slug,
            'city': city,
            'name': name,
            'event_id': v['id'] + 1000000,
            'lat': v.get('lat'),
            'lng': v.get('lng'),
            'days': v.get('days'),
            'labels': v.get('labels'),
            'note': v.get('note'),
            'image': v.get('image'),
            'gmaps': v.get('gmaps'),
            'link': v.get('link'),
        }
    )

@app.route('/event/<int:event_id>')
def event_page(event_id):
    db = get_db()
    row = db.execute('''
        SELECT e.*, c.name as community_name, c.image as community_image,
               v.name as venue_name, v.city as city,
               v.lat as venue_lat, v.lng as venue_lng
        FROM events e
        LEFT JOIN communities c ON e.community_id = c.id
        LEFT JOIN venues v ON e.venue_id = v.id
        WHERE e.id = ?
    ''', (event_id,)).fetchone()
    if not row:
        abort(404)
    ev = dict(row)
    city = ev.get('city', '')
    name = ev.get('title', '')
    venue = ev.get('venue_name', '')
    desc_parts = [f"Chess in {city}"]
    if venue:
        desc_parts.append(f"at {venue}")
    if ev.get('notes'):
        desc_parts.append(ev['notes'])
    return render_template('index.html',
        og_title=f"{name} · Chess Scenes",
        og_description=" · ".join(desc_parts),
        og_image=ev.get('community_image'),
        og_url=f"/event/{event_id}",
        initial_data={
            'type': 'event',
            'id': event_id,
            'city': city,
            'name': name,
            'lat': ev.get('venue_lat'),
            'lng': ev.get('venue_lng'),
        }
    )

@app.route('/admin')
def admin():
    return render_template('admin.html')

if __name__ == '__main__':
    init_db()
    seed_db()
    seed_directory()
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=False, host='0.0.0.0', port=port)
