"""
Seed script — reads CSV and populates Chess Scenes via the admin API.

Usage:
    python3 seed.py --csv ~/Downloads/chessscenesdatapublic.csv --url https://chessscenes.com
    python3 seed.py --csv ~/Downloads/chessscenesdatapublic.csv --url https://web-production-76e2f.up.railway.app

You will be prompted for your admin username and password.
"""
import argparse
import csv
import getpass
import json
import sys
import urllib.request
import urllib.error

# Map full day names to short codes
DAY_MAP = {
    "monday": "mon", "tuesday": "tue", "wednesday": "wed",
    "thursday": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun",
}

# Map CSV label values to API type codes (first label wins for multi-type places)
TYPE_MAP = {
    "chess club":     "chess_club",
    "chess bar":      "chess_bar",
    "chess meetup":   "chess_meetup",
    "chess board":    "chess_board",
    "chess shop":     "chess_shop",
    "chess memorial": "chess_memorial",
    "chess museum":   "chess_museum",
}


def parse_days(raw):
    """Convert "Monday, Wednesday, Friday" → "mon,wed,fri" """
    if not raw.strip():
        return ""
    parts = [p.strip().lower() for p in raw.split(",")]
    codes = [DAY_MAP[p] for p in parts if p in DAY_MAP]
    return ",".join(codes)


def parse_type(raw):
    """Convert all labels to type codes, comma-separated."""
    codes = [TYPE_MAP[p.strip().lower()] for p in raw.split(",") if p.strip().lower() in TYPE_MAP]
    return ",".join(codes)


def coords_distance_m(lat1, lng1, lat2, lng2):
    """Approximate distance in metres between two lat/lng points."""
    import math
    R = 6_371_000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_match(place, existing):
    """Return matching existing place dict, or None.

    Match criteria (any one is sufficient):
    - Same name + same city (case-insensitive)
    - Coordinates within 100 m of an existing place
    - Exact name match (regardless of city)
    """
    name = place["name"].lower()
    city = (place["city"] or "").lower()
    lat, lng = place["lat"], place["lng"]

    for e in existing:
        e_name = (e.get("name") or "").lower()
        e_city = (e.get("city") or "").lower()
        e_lat, e_lng = e.get("lat"), e.get("lng")

        if e_name == name and e_city == city:
            return e
        if lat and lng and e_lat and e_lng:
            if coords_distance_m(lat, lng, e_lat, e_lng) < 100:
                return e
        if e_name == name:
            return e

    return None


def parse_coords(raw):
    """Parse "52.3755, 4.8826" into (lat, lng) floats."""
    if not raw.strip():
        return None, None
    parts = raw.split(",")
    if len(parts) == 2:
        try:
            return float(parts[0].strip()), float(parts[1].strip())
        except ValueError:
            pass
    return None, None


def api_request(base_url, method, path, data, token=None):
    payload = json.dumps(data).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base_url}{path}", data=payload, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def api_get(base_url, path, token):
    headers = {"Authorization": f"Bearer {token}"}
    req = urllib.request.Request(f"{base_url}{path}", headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def login(base_url, username, password):
    result = api_request(base_url, "POST", "/api/auth/login", {"username": username, "password": password})
    return result["token"]


def seed(csv_path, base_url, token, limit=None):
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    if limit:
        rows = rows[:limit]

    # Fetch existing places for duplicate detection
    existing = api_get(base_url, "/api/admin/places", token)

    inserted = updated = skipped = 0
    print(f"Seeding {len(rows)} rows ({len(existing)} places already in DB)...\n")

    for row in rows:
        name = row.get("name", "").strip()
        if not name:
            skipped += 1
            continue

        lat, lng = parse_coords(row.get("coordinates", ""))

        place = {
            "name":           name,
            "city":           row.get("city", "").strip(),
            "country":        row.get("country", "").strip(),
            "lat":            lat,
            "lng":            lng,
            "type":           parse_type(row.get("labels", "")),
            "description":    row.get("note", "").strip(),
            "schedule_days":  parse_days(row.get("days", "")),
            "schedule_notes": "",
            "website":        row.get("link", "").strip() or None,
            "maps_url":       row.get("gmap", "").strip() or None,
            "image_url":      row.get("image", "").strip() or None,
            "verified":       True,
            "active":         True,
        }

        try:
            match = find_match(place, existing)
            if match:
                api_request(base_url, "PUT", f"/api/admin/places/{match['id']}", place, token)
                print(f"  ~ {name} (updated, matched '{match['name']}')")
                updated += 1
            else:
                api_request(base_url, "POST", "/api/admin/places", place, token)
                print(f"  + {name}")
                inserted += 1
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"  ✗ {name}: {e.code} {body}")
            skipped += 1

    print(f"\nDone. Inserted: {inserted}  Updated: {updated}  Skipped: {skipped}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to CSV file")
    parser.add_argument("--url", default="http://localhost:5001", help="API base URL")
    parser.add_argument("--limit", type=int, help="Only seed the first N rows")
    args = parser.parse_args()

    username = input("Admin username: ")
    password = getpass.getpass("Admin password: ")

    print("Logging in...")
    try:
        token = login(args.url, username, password)
    except Exception as e:
        print(f"Login failed: {e}")
        sys.exit(1)

    print("Logged in. Seeding...")
    seed(args.csv, args.url, token, limit=args.limit)


if __name__ == "__main__":
    main()
