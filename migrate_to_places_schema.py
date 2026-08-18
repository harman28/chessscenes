#!/usr/bin/env python3
"""
One-off migration: venue_directory + hardcoded seed_db() -> places CSV + chess_scenes_events.json.

Run once, inspect the output, commit it. Not meant to run again — chess_scenes_schema.py
(the new app.py seeding code) reads the files this script produces, not the old
venue_directory/venues/events tables.

What this does, and why:

1. Reads the current CSV (venue_directory's source). 9 of its rows are pre-existing
   duplicates: entries named after a COMMUNITY (e.g. "Zwart op Wit") rather than the
   physical place, sitting at the exact same coordinates/gmaps link as a place that's
   *also* hardcoded into seed_db()'s venues/events lists (e.g. "2 Klaveren"). The old
   app hid this at query time via name/gmaps matching (see the removed comments in
   app.py's fetch_events()/venue_directory()); this migration removes the duplicate
   data instead of re-implementing that workaround against the new schema. Verified by
   cross-checking every hardcoded venue's gmaps link against the full CSV before writing
   this list — see DROP_ALIAS_PLACE_NAMES.
2. Adds the 10 venues that only ever existed in the hardcoded seed_db() venues list
   (never had a CSV row at all) as real places.
3. Writes chess_scenes_events.json: one entry per hardcoded seed_db() event (resolved to
   the correct place slug) plus one entry per remaining CSV row that had `days` set.
   Chess & Beer is written with active=false (no longer meets, per Harman). Barblitz
   Amsterdam gets no event here — its real schedule comes from barblitz_scraper.py.
4. Rewrites the places CSV without the `days` column (schedule now lives in the events
   JSON) and without the 9 duplicate rows, keeping every other existing column as-is.
"""

import csv
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent
CSV_PATH = REPO_ROOT / "Chess Scenes (Public) - chess_scenes_venues.csv"
EVENTS_JSON_PATH = REPO_ROOT / "chess_scenes_events.json"


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return re.sub(r'-+', '-', text).strip('-')


# Names of CSV rows that are community aliases for a place already listed in
# NEW_PLACES / already present under its real name in the CSV — confirmed via
# gmaps-link cross-check against every hardcoded venue (see module docstring).
DROP_ALIAS_PLACE_NAMES = {
    "Zwart op Wit", "Schaakvereniging Amsterdam West", "Schaakvereniging Caissa",
    "Pegasus Amstelveen", "Schaakvereniging EsPion", "De Queer Schaakclub",
    "De Volewijckers", "Chess & Beer", "Amsterdam Spirit Chess Club",
}

# Venues that only existed in the old hardcoded seed_db() venues list — never had a
# CSV/venue_directory row, so their `labels` had to be judgment calls rather than existing
# data. First pass got 3 of 9 wrong (2 Klaveren, Bilderdijkpark, Vondelbunker, then KLABU
# Clubhouse) — caught via the pin-icon feature showing the wrong piece. The reliable signal
# was already sitting in HARDCODED_EVENTS the whole time: format_tag "Club night" means a
# formal club (schaakvereniging), "Casual" doesn't — even when the venue/community name has
# "club" in it (KLABU Clubhouse hosting "Amsterdam Spirit Chess Club" is tagged Casual, not
# Club night, so it's a meetup, not a club). (name, labels, gmaps, lat, lng, city)
NEW_PLACES = [
    ("2 Klaveren", "chess club", "https://maps.app.goo.gl/2iYpS9ALfHsJLAwYA", 52.3711, 4.8662, "Amsterdam"),
    ("Bilderdijkpark", "chess club", "https://maps.app.goo.gl/HE7btnNk4Bit5ywy8", 52.3718, 4.8688, "Amsterdam"),
    ("Huize Lydia", "chess club", "https://maps.app.goo.gl/cnJ446iJsELTRz7XA", 52.3532, 4.8833, "Amsterdam"),
    ("La Plaza, Groenelaan", "chess club", "https://maps.app.goo.gl/3msMbTPckGVqGh9d9", 52.2926, 4.8745, "Amsterdam"),
    ("Gaaspstraat 8", "chess club", "https://maps.app.goo.gl/dZG9V7rcx1a9q3rLA", 52.3452, 4.9085, "Amsterdam"),
    ("Speelzaal KLUP", "chess club", "https://maps.app.goo.gl/4hLHEWU5ktfCiWCXA", 52.3544, 4.8545, "Amsterdam"),
    ("Het Zwanenmeer", "chess club", "https://maps.app.goo.gl/mqUyi83fLoGxKCwi8", 52.3956, 4.9499, "Amsterdam"),
    ("Vondelbunker", "chess meetup", "https://maps.app.goo.gl/zVaGJ4eQ19HZ6h6z8", 52.3609, 4.8776, "Amsterdam"),
    ("KLABU Clubhouse", "chess meetup", "https://maps.app.goo.gl/Hwt9yytsy1LJbFCa8", 52.3831, 4.8865, "Amsterdam"),
]
# Cafe De Balie is deliberately NOT a place — it isn't a chess place in its own right, it
# was only ever the venue for Chess & Beer (now inactive, see STANDALONE_EVENTS below). Same
# principle as Barblitz's other bars: don't create a permanent pin for a one-off/ended use.

COMMUNITIES = {
    "Zwart op Wit": "https://i.imgur.com/8jibVQ6.jpeg",
    "Schaakvereniging Amsterdam West": "https://i.imgur.com/inhlo0q.jpeg",
    "Schaakvereniging Caissa": "https://i.imgur.com/S7Sk0IW.jpeg",
    "Pegasus Amstelveen": "https://i.imgur.com/RHugkLY.jpeg",
    "Schaakvereniging EsPion": "https://i.imgur.com/nlSMpwC.jpeg",
    "De Queer Schaakclub": "https://i.imgur.com/G6UwvNd.jpeg",
    "De Volewijckers": None,
    "Max Euwe Centrum": "https://i.imgur.com/inTkxpx.jpeg",
    "Chess & Beer": "https://i.imgur.com/RTWaMou.png",
    "Vondelbunker Chess": "https://i.imgur.com/zgYqQLp.png",
    "Amsterdam Spirit Chess Club": "https://i.imgur.com/qrvUv5i.png",
    "BarBlitz": "https://barblitz.co/static/chess/images/new_logo.4c6a6f89e4c5.png",
    "Cafe de Laurierboom": "https://i.imgur.com/9NRex3f.jpeg",
    "Schaakcafe Utrecht": "https://i.imgur.com/wlhqWob.jpeg",
    "Stichting En Passant": "https://i.imgur.com/fVrdQDp.jpeg",
    "KopieKoffie": "https://i.imgur.com/pC1qmvK.jpeg",
}

ALL_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# (community, place_name, title, time, time_end, format_tag, external_link, notes, days, active)
HARDCODED_EVENTS = [
    ("Zwart op Wit", "2 Klaveren", "Zwart op Wit Club Night", "20:00", None, "Club night", "https://www.zwartopwit.org/", None, ["Monday"], True),
    ("Schaakvereniging EsPion", "Gaaspstraat 8", "EsPion Club Night", "20:00", None, "Club night", "https://www.espion.nl/", None, ["Monday"], True),
    ("Schaakvereniging Caissa", "Huize Lydia", "Caissa Club Night", "20:00", None, "Club night", "http://www.caissa-amsterdam.nl/", None, ["Tuesday"], True),
    ("Pegasus Amstelveen", "La Plaza, Groenelaan", "Pegasus Club Night", "19:45", None, "Club night", "https://www.pegasusamstelveen.nl", None, ["Tuesday"], True),
    ("De Queer Schaakclub", "Speelzaal KLUP", "De Queer Schaakclub", "20:00", None, "Club night", "https://dequeerschaakclub.nl/", None, ["Wednesday"], True),
    ("De Volewijckers", "Het Zwanenmeer", "De Volewijckers Club Night", "20:00", None, "Club night", "https://www.schaakverenigingdevolewijckers.nl/", None, ["Wednesday"], True),
    ("Schaakvereniging Amsterdam West", "Bilderdijkpark", "Amsterdam West Club Night", "20:00", None, "Club night", "https://www.svamsterdamwest.nl/", None, ["Thursday"], True),
    ("Max Euwe Centrum", "Max Euwe Centrum", "Max Euwe Centrum Open Hours", "10:00", "16:00", "Open play", "https://maxeuwe.nl/", "Open Tue–Sat", ["Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"], True),
    ("Vondelbunker Chess", "Vondelbunker", "Vondelbunker Chess", "14:00", None, "Casual", "https://radar.squat.net/en/event/amsterdam/vondelbunker/2026-05-17/bunker-chess-club", "Irregular — check link", ["Sunday"], True),
    ("Amsterdam Spirit Chess Club", "KLABU Clubhouse", "Amsterdam Spirit Chess Club", "15:00", "18:00", "Casual", "https://klabu.org/clubhouses/amsterdam", None, ["Sunday"], True),
    ("Cafe de Laurierboom", "Cafe de Laurierboom", "Cafe de Laurierboom", "15:00", None, "Casual", "https://maps.app.goo.gl/PizEC9TRQ4kt8QyK6", "Hours vary: Wed–Thu until 01:00, Fri–Sat until 03:00, Sun–Tue until 01:00", ALL_DAYS, True),
    ("Schaakcafe Utrecht", "Schaakcafe Utrecht", "Schaakcafe Utrecht", "13:30", "17:00", "Casual", "https://www.schakeninutrecht.nl/schaakcafe/", None, ["Friday"], True),
    ("Stichting En Passant", "Stichting En Passant", "Stichting En Passant", "14:00", None, "Club night", "https://www.stichtingenpassant.nl/", "Chess on weekends.", ["Friday", "Saturday", "Sunday"], True),
    ("KopieKoffie", "KopieKoffie", "KopieKoffie Chess", "15:30", None, "Casual", "https://kopiekoffie.nl/blog/events/schaken-bij-kopiekoffie/", None, ["Sunday"], True),
]
# BarBlitz is intentionally absent here — no invented schedule.
# It still needs a communities row (see COMMUNITIES above) so it exists once
# barblitz_scraper.py starts adding real dated events.

# Events with no place_id at all — the venue isn't (or is no longer) a chess place in its
# own right, so it never gets a permanent pin. (community, title, standalone_name,
# standalone_lat, standalone_lng, standalone_gmaps, standalone_city, time, time_end, fmt,
# link, notes, days, active)
STANDALONE_EVENTS = [
    ("Chess & Beer", "Chess & Beer", "Cafe De Balie", 52.3632, 4.883,
     "https://maps.app.goo.gl/bkpboKbMJeadL65F6", "Amsterdam", "14:00", None, "Casual",
     "https://www.meetup.com/amsterdam-chess-and-beer/", "Every second Sunday", ["Sunday"], False),
]


def main():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        old_rows = list(csv.DictReader(f))

    seen_slugs = set()
    place_slug_by_name = {}  # name.lower() -> slug, for resolving hardcoded events
    place_rows = []  # rows for the new places CSV (dict form)

    def add_place(name, labels, city, lat, lng, gmaps, link, image, note):
        if not lat or not lng:
            raise SystemExit(f"Place {name!r} has no coordinates — places require lat/lng")
        base = slugify(name)
        slug = base
        if slug in seen_slugs:
            slug = base + "-" + slugify(city)
        counter = 2
        while slug in seen_slugs:
            slug = base + "-" + str(counter)
            counter += 1
        seen_slugs.add(slug)
        place_slug_by_name[name.lower()] = slug
        place_rows.append({
            "name": name, "labels": labels or "", "city": city,
            "coordinates": f"{lat}, {lng}", "note": note or "",
            "gmap": gmaps or "", "link": link or "", "image": image or "",
            "slug": slug, "id": "",
        })

    dropped = 0
    for row in old_rows:
        name = row["name"].strip()
        if name in DROP_ALIAS_PLACE_NAMES:
            dropped += 1
            continue
        coords = row["coordinates"].strip()
        lat_str, lng_str = "", ""
        if coords and "," in coords:
            lat_str, lng_str = [p.strip() for p in coords.split(",", 1)]
        add_place(
            name, row["labels"].strip(), row["city"].strip(),
            lat_str, lng_str, row["gmap"].strip(),
            row["link"].strip(), row["image"].strip(), row["note"].strip(),
        )

    print(f"Dropped {dropped} community-alias duplicate rows: {sorted(DROP_ALIAS_PLACE_NAMES)}")

    for name, labels, gmaps, lat, lng, city in NEW_PLACES:
        add_place(name, labels, city, lat, lng, gmaps, None, None, None)

    print(f"Added {len(NEW_PLACES)} new places that only existed in the old hardcoded venues list")

    events = []
    csv_days_used_names = set()
    for community, place_name, title, time_, time_end, fmt, link, notes, days, active in HARDCODED_EVENTS:
        slug = place_slug_by_name.get(place_name.lower())
        if not slug:
            raise SystemExit(f"No place found for hardcoded event venue {place_name!r}")
        events.append({
            "place_slug": slug, "community": community, "title": title,
            "time": time_, "time_end": time_end, "format_tag": fmt,
            "external_link": link, "notes": notes, "days": days,
            "specific_date": None, "active": active,
        })
        csv_days_used_names.add(place_name.lower())

    for community, title, s_name, s_lat, s_lng, s_gmaps, s_city, time_, time_end, fmt, link, notes, days, active in STANDALONE_EVENTS:
        events.append({
            "place_slug": None, "standalone_name": s_name, "standalone_city": s_city,
            "standalone_lat": s_lat, "standalone_lng": s_lng, "standalone_gmaps": s_gmaps,
            "community": community, "title": title, "time": time_, "time_end": time_end,
            "format_tag": fmt, "external_link": link, "notes": notes, "days": days,
            "specific_date": None, "active": active,
        })

    for row in old_rows:
        name = row["name"].strip()
        days_str = row["days"].strip()
        if not days_str or name in DROP_ALIAS_PLACE_NAMES:
            continue
        if name.lower() in csv_days_used_names:
            continue  # already covered by a richer hardcoded event above
        slug = place_slug_by_name.get(name.lower())
        if not slug:
            continue
        events.append({
            "place_slug": slug, "community": None, "title": name,
            "time": None, "time_end": None, "format_tag": None,
            "external_link": row["link"].strip() or None,
            "notes": row["note"].strip() or None,
            "days": [d.strip() for d in days_str.split(",") if d.strip()],
            "specific_date": None, "active": True,
        })

    print(f"Wrote {len(events)} events ({len(HARDCODED_EVENTS)} hardcoded + "
          f"{len(events) - len(HARDCODED_EVENTS)} from CSV `days` columns)")

    EVENTS_JSON_PATH.write_text(
        json.dumps({"communities": COMMUNITIES, "events": events}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    fieldnames = ["name", "labels", "city", "coordinates", "note", "gmap", "link", "image", "slug", "id"]
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(place_rows)

    print(f"Wrote {len(place_rows)} places to CSV (was {len(old_rows)} rows, "
          f"-{dropped} duplicates +{len(NEW_PLACES)} newly-added)")


if __name__ == "__main__":
    main()
