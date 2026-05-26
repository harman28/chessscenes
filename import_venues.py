import csv
import sqlite3

conn = sqlite3.connect('chess.db')
cur = conn.cursor()

updated, inserted = 0, 0

with open('Chess Scenes (Public) - chess_scenes_venues.csv', newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        name   = row['name'].strip()
        labels = row['labels'].strip() or None
        city   = row['city'].strip()
        note   = row['note'].strip() or None
        gmaps  = row['gmap'].strip() or None
        link   = row['link'].strip() or None
        image  = row['image'].strip() or None

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

        cur.execute('SELECT id FROM venue_directory WHERE name=? AND city=?', (name, city))
        existing = cur.fetchone()

        if existing:
            cur.execute('''UPDATE venue_directory
                           SET labels=?, lat=?, lng=?, note=?, gmaps=?, link=?, image=?
                           WHERE id=?''',
                        (labels, lat, lng, note, gmaps, link, image, existing[0]))
            updated += 1
            print(f'  updated : {name} ({city})')
        else:
            cur.execute('''INSERT INTO venue_directory (name, labels, city, lat, lng, note, gmaps, link, image)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (name, labels, city, lat, lng, note, gmaps, link, image))
            inserted += 1
            print(f'  inserted: {name} ({city})')

conn.commit()
conn.close()
print(f'\nDone — {inserted} inserted, {updated} updated.')
