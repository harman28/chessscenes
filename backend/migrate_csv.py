"""
Standalone migration script — no Flask required.
Reads the Chess Scenes CSV and inserts into chess.db directly via sqlite3.

Usage (from backend/ folder, with venv active):
    python3 migrate_csv.py --csv path/to/venues.csv

CSV columns expected:
    name, labels, city, coordinates, note, gmap, link, image, days, id
"""
import argparse
import csv
import re
import sqlite3
import os
import sys


def slugify(text):
    text = text.lower().strip()
    text = text.encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def unique_slug(conn, base):
    slug, i = base, 2
    while conn.execute("SELECT id FROM places WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{i}"
        i += 1
    return slug


def days_to_schedule_days(days_str):
    """Convert 'Monday, Wednesday' → 'mon,wed'"""
    if not days_str.strip():
        return ""
    mapping = {
        "monday": "mon", "tuesday": "tue", "wednesday": "wed",
        "thursday": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun"
    }
    parts = [d.strip().lower() for d in days_str.split(",")]
    return ",".join(mapping.get(p, p[:3]) for p in parts if p)


def map_type(labels_str):
    """Take the first label as the canonical 'type' field, normalise spacing."""
    first = labels_str.split(",")[0].strip().lower()
    # Normalise to underscore format used in our schema
    return first.replace(" ", "_") if first else ""


def run(csv_path, db_path):
    if not os.path.exists(db_path):
        print(f"ERROR: database not found at {db_path}")
        print("Make sure you've started the Flask app at least once so it creates chess.db")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    inserted = skipped = updated = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip()
            if not name:
                skipped += 1
                continue

            # Parse coordinates — "lat, lng" in a single field
            coords = row.get("coordinates", "").strip().strip('"')
            lat = lng = None
            if coords:
                parts = coords.split(",")
                if len(parts) == 2:
                    try:
                        lat = float(parts[0].strip())
                        lng = float(parts[1].strip())
                    except ValueError:
                        pass

            city      = row.get("city", "").strip()
            labels    = row.get("labels", "").strip()
            note      = row.get("note", "").strip()
            gmap      = row.get("gmap", "").strip()
            link      = row.get("link", "").strip()
            image_url = row.get("image", "").strip()
            days_raw  = row.get("days", "").strip()
            csv_id    = row.get("id", "").strip()

            type_val       = map_type(labels)
            schedule_days  = days_to_schedule_days(days_raw)
            schedule_notes = days_raw  # keep human-readable original too
            website        = link or gmap  # prefer link, fall back to gmap

            # Derive country from city — basic lookup for known cities
            # You can extend this or update directly in the DB later
            CITY_COUNTRY = {
                "Amsterdam": "Netherlands", "Utrecht": "Netherlands",
                "Leiden": "Netherlands", "Gouda": "Netherlands",
                "The Hague": "Netherlands", "Delft": "Netherlands",
                "Ghent": "Belgium", "Brussels": "Belgium",
                "Cork": "Ireland", "Dublin": "Ireland",
                "Inverness": "UK", "Bristol": "UK", "London": "UK",
                "Luxembourg": "Luxembourg",
                "Cologne": "Germany", "Berlin": "Germany",
                "Hamburg": "Germany",
                "Copenhagen": "Denmark",
                "Stockholm": "Sweden", "Göteborg": "Sweden",
                "Helsinki": "Finland",
                "Oslo": "Norway",
                "Riga": "Latvia",
                "Krakow": "Poland",
                "Budapest": "Hungary",
                "Belgrade": "Serbia", "Vrnjačka Banja": "Serbia",
                "Bucharest": "Romania", "Sibiu": "Romania",
                "Athens": "Greece",
                "Geneva": "Switzerland", "Basel": "Switzerland", "Zurich": "Switzerland",
                "Prague": "Czech Republic",
                "Barcelona": "Spain",
                "Marostica": "Italy",
                "Lille": "France", "Paris": "France",
                "Moscow": "Russia",
                "Ankara": "Turkey",
                "Reykjavik": "Iceland", "Selfoss": "Iceland",
                "Mumbai": "India", "Delhi": "India", "Pune": "India",
                "Thiruvananthapuram": "India",
                "Mexico City": "Mexico",
                "Lima": "Peru",
                "Santiago": "Chile",
                "New York": "USA", "Philadelphia": "USA", "Charlotte": "USA",
                "Atlanta": "USA", "St. Louis": "USA", "Chicago": "USA",
                "Toronto": "Canada",
                "Cape Town": "South Africa",
                "Sydney": "Australia",
                "Tokyo": "Japan",
            }
            country = CITY_COUNTRY.get(city, "")

            # Use csv id as slug base if present, otherwise derive from name+city
            if csv_id:
                base_slug = slugify(csv_id)
            else:
                base_slug = slugify(f"{city}-{name}" if city else name)

            slug = unique_slug(conn, base_slug)

            try:
                conn.execute("""
                    INSERT INTO places
                        (name, slug, city, country, lat, lng, type, description,
                         schedule_notes, schedule_days, website, image_url,
                         verified, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
                """, (
                    name, slug, city, country, lat, lng,
                    type_val, note,
                    schedule_notes, schedule_days,
                    website, image_url,
                ))
                inserted += 1
            except sqlite3.IntegrityError as e:
                print(f"  Skipped '{name}': {e}")
                skipped += 1
            except Exception as e:
                print(f"  Error on '{name}': {e}")
                skipped += 1

    conn.commit()
    conn.close()
    print(f"\nDone.  Inserted: {inserted}  Skipped: {skipped}")
    print(f"Database: {os.path.abspath(db_path)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to CSV file")
    parser.add_argument("--db",  default="chess.db", help="Path to SQLite DB (default: chess.db)")
    args = parser.parse_args()
    run(args.csv, args.db)
