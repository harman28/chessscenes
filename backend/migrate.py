"""
Migrate CSV venue data into the Chess Scenes SQLite database.

Usage:
    python migrate.py --csv path/to/venues.csv [--db chess.db]

Expected CSV columns (flexible — see COLUMN_MAP for accepted aliases):
    name, city, country, lat, lng, type, description,
    schedule_notes, schedule_days, website, image_url, verified
"""
import argparse
import csv
import re
import sys
import os

# Allow running from backend/ directly
sys.path.insert(0, os.path.dirname(__file__))

COLUMN_MAP = {
    "name": "name",
    "city": "city",
    "country": "country",
    "lat": "lat", "latitude": "lat",
    "lng": "lng", "lon": "lng", "longitude": "lng",
    "type": "type",
    "description": "description", "desc": "description",
    "schedule_notes": "schedule_notes", "notes": "schedule_notes", "schedule": "schedule_notes",
    "schedule_days": "schedule_days", "days": "schedule_days",
    "website": "website", "url": "website", "link": "website",
    "image_url": "image_url", "image": "image_url", "photo": "image_url",
    "maps_url": "maps_url", "gmap": "maps_url", "gmaps": "maps_url", "google_maps": "maps_url",
    "verified": "verified",
}


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text


def unique_slug(session, Place, base):
    from sqlalchemy import func
    slug, i = base, 2
    while session.query(Place).filter_by(slug=slug).first():
        slug = f"{base}-{i}"
        i += 1
    return slug


def run(csv_path, db_path):
    # Bootstrap Flask app context
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{db_path}")
    from app import create_app
    from extensions import db
    from models import Place

    app = create_app()
    inserted = skipped = 0

    with app.app_context():
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Normalise column names
                norm = {}
                for k, v in row.items():
                    mapped = COLUMN_MAP.get(k.strip().lower())
                    if mapped:
                        norm[mapped] = v.strip()

                name = norm.get("name")
                if not name:
                    skipped += 1
                    continue

                slug = unique_slug(db.session, Place, slugify(name))
                try:
                    lat = float(norm["lat"]) if norm.get("lat") else None
                    lng = float(norm["lng"]) if norm.get("lng") else None
                    verified_raw = norm.get("verified", "1").lower()
                    verified = verified_raw in ("1", "true", "yes")

                    place = Place(
                        name=name, slug=slug,
                        city=norm.get("city", ""),
                        country=norm.get("country", ""),
                        lat=lat, lng=lng,
                        type=norm.get("type", ""),
                        description=norm.get("description", ""),
                        schedule_notes=norm.get("schedule_notes", ""),
                        schedule_days=norm.get("schedule_days", ""),
                        website=norm.get("website", ""),
                        image_url=norm.get("image_url", ""),
                        maps_url=norm.get("maps_url", "") or None,
                        verified=verified,
                        active=True,
                    )
                    db.session.add(place)
                    db.session.flush()
                    inserted += 1
                except Exception as e:
                    print(f"  Skipped '{name}': {e}")
                    db.session.rollback()
                    skipped += 1

            db.session.commit()

    print(f"\nDone. Inserted: {inserted}  Skipped: {skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to CSV file")
    parser.add_argument("--db", default="chess.db", help="Path to SQLite DB (default: chess.db)")
    args = parser.parse_args()
    run(args.csv, args.db)
