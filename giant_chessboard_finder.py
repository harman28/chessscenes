#!/usr/bin/env python3
"""
Giant Chessboard Finder for chessscenes.com.

Sweeps OpenStreetMap via the Overpass API for outdoor giant chessboards
worldwide, dedupes results within ~50m of each other, reverse-geocodes each
cluster to a city/country via Nominatim, flags likely-already-known venues
by proximity to the existing directory, and writes review-ready CSV + JSON.

Nothing here is auto-published. OSM's sport=chess tag (and the free-text
fallback) are noisy — indoor board-game cafes, regular playground pitches,
and mistagged nodes all show up — so every hit needs a human to confirm via
photo/Street View before it's promoted into the CSV/chess.db.

Needs real internet access to overpass-api.de and nominatim.openstreetmap.org.
Run it locally, or via the "Giant Chessboard Finder" GitHub Actions workflow
(.github/workflows/giant_chessboard_finder.yml) which runs on GitHub's own
runners — the same pattern already used for scout.py/scout.yml. It will NOT
work from a network-sandboxed session that blocks those hosts.

Usage:
    python3 giant_chessboard_finder.py
    python3 giant_chessboard_finder.py --skip-geocode        # faster, no city/country
    python3 giant_chessboard_finder.py --out-dir /tmp/out
    python3 giant_chessboard_finder.py --tagged-json f1.json --freetext-json f2.json
        # offline/test mode: read raw Overpass responses from local files instead
        # of hitting the live API (used by test_giant_chessboard_finder.py)
"""

import argparse
import csv
import json
import math
import sqlite3
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).parent
CSV_PATH = REPO_ROOT / "Chess Scenes (Public) - chess_scenes_venues.csv"
DB_PATH = REPO_ROOT / "chess.db"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "ChessScenesGiantChessboardFinder/1.0 (+https://chessscenes.com)"

DEDUPE_RADIUS_M = 50
EXISTING_MATCH_RADIUS_M = 100
NOMINATIM_DELAY_S = 1.1  # Nominatim usage policy: max 1 req/sec, no bulk hammering
OVERPASS_TIMEOUT_S = 200
OVERPASS_RETRIES = 3
OVERPASS_BACKOFF_S = (5, 15, 45)

QUERY_TAGGED = """
[out:json][timeout:180];
(
  node["sport"="chess"];
  way["sport"="chess"];
  node["leisure"="pitch"]["sport"="chess"];
);
out center;
"""

QUERY_FREETEXT = """
[out:json][timeout:180];
(
  node["name"~"schaakbord|chess board|chessboard|giant chess|xadrez gigante|scacchiera gigante",i];
  node["description"~"schaakbord|chess board|chessboard|giant chess",i];
);
out center;
"""

QUERIES = [
    ("tagged", QUERY_TAGGED),
    ("freetext", QUERY_FREETEXT),
]


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def run_overpass_query(query, label):
    """POST a query to the live Overpass API with retries. Returns raw elements list."""
    last_err = None
    for attempt in range(OVERPASS_RETRIES):
        try:
            resp = requests.post(
                OVERPASS_URL,
                data={"data": query},
                headers={"User-Agent": USER_AGENT},
                timeout=OVERPASS_TIMEOUT_S,
            )
            if resp.status_code == 200:
                return resp.json().get("elements", [])
            last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except requests.RequestException as e:
            last_err = str(e)
        if attempt < OVERPASS_RETRIES - 1:
            wait = OVERPASS_BACKOFF_S[min(attempt, len(OVERPASS_BACKOFF_S) - 1)]
            print(f"  [{label}] attempt {attempt + 1} failed ({last_err}); retrying in {wait}s...", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"Overpass query '{label}' failed after {OVERPASS_RETRIES} attempts: {last_err}")


def elements_to_candidates(elements, query_label):
    """Turn raw Overpass elements (nodes/ways with 'out center') into unified candidates."""
    candidates = []
    for el in elements:
        osm_type = el.get("type")
        osm_id = el.get("id")
        if osm_type == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            center = el.get("center") or {}
            lat, lon = center.get("lat"), center.get("lon")
        if lat is None or lon is None:
            continue
        candidates.append(
            {
                "osm_type": osm_type,
                "osm_id": osm_id,
                "lat": lat,
                "lon": lon,
                "tags": el.get("tags", {}) or {},
                "matched_by": {query_label},
            }
        )
    return candidates


def merge_by_osm_id(candidates):
    """Collapse exact-same OSM element hits (e.g. matched by both queries) into one."""
    by_key = {}
    for c in candidates:
        key = (c["osm_type"], c["osm_id"])
        if key in by_key:
            by_key[key]["matched_by"] |= c["matched_by"]
        else:
            by_key[key] = dict(c)
    return list(by_key.values())


def spatial_dedupe(candidates, radius_m=DEDUPE_RADIUS_M):
    """
    Greedy clustering: group candidates within radius_m of each other.
    Uses a coarse lat/lon grid bucket (~0.001deg ~= 111m) so we only compare
    each candidate against nearby buckets instead of doing O(n^2) globally.
    """
    cell_deg = 0.001
    buckets = {}
    for c in candidates:
        key = (round(c["lat"] / cell_deg), round(c["lon"] / cell_deg))
        buckets.setdefault(key, []).append(c)

    clusters = []
    assigned = set()
    for c in candidates:
        cid = id(c)
        if cid in assigned:
            continue
        cell = (round(c["lat"] / cell_deg), round(c["lon"] / cell_deg))
        neighbor_cells = [
            (cell[0] + dx, cell[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
        ]
        members = [c]
        assigned.add(cid)
        for nc in neighbor_cells:
            for other in buckets.get(nc, []):
                oid = id(other)
                if oid in assigned:
                    continue
                if haversine_m(c["lat"], c["lon"], other["lat"], other["lon"]) <= radius_m:
                    members.append(other)
                    assigned.add(oid)
        clusters.append(members)

    merged = []
    for members in clusters:
        primary = next((m for m in members if m["tags"].get("name")), members[0])
        matched_by = set()
        all_osm_refs = []
        for m in members:
            matched_by |= m["matched_by"]
            all_osm_refs.append(f"{m['osm_type']}/{m['osm_id']}")
        merged.append(
            {
                "osm_type": primary["osm_type"],
                "osm_id": primary["osm_id"],
                "lat": primary["lat"],
                "lon": primary["lon"],
                "tags": primary["tags"],
                "matched_by": matched_by,
                "cluster_osm_refs": all_osm_refs,
                "cluster_size": len(members),
            }
        )
    return merged


def load_existing_venues():
    """Read (name, city, lat, lng) for every existing venue from the CSV (source of truth)."""
    existing = []
    if not CSV_PATH.exists():
        return existing
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            coords = (row.get("coordinates") or "").strip()
            if not coords:
                continue
            parts = coords.split(",")
            if len(parts) != 2:
                continue
            try:
                lat, lng = float(parts[0].strip()), float(parts[1].strip())
            except ValueError:
                continue
            existing.append({"name": row["name"].strip(), "city": row["city"].strip(), "lat": lat, "lng": lng})
    return existing


def flag_possible_duplicates(clusters, existing_venues, radius_m=EXISTING_MATCH_RADIUS_M):
    for cluster in clusters:
        best = None
        best_dist = None
        for v in existing_venues:
            d = haversine_m(cluster["lat"], cluster["lon"], v["lat"], v["lng"])
            if d <= radius_m and (best_dist is None or d < best_dist):
                best, best_dist = v, d
        if best:
            cluster["possible_duplicate_of"] = f"{best['name']} ({best['city']})"
            cluster["duplicate_distance_m"] = round(best_dist, 1)
        else:
            cluster["possible_duplicate_of"] = ""
            cluster["duplicate_distance_m"] = None


_geocode_cache = {}


def reverse_geocode(lat, lon):
    """Reverse-geocode via Nominatim, respecting its 1 req/sec usage policy. Cached."""
    key = (round(lat, 3), round(lon, 3))
    if key in _geocode_cache:
        return _geocode_cache[key]
    result = {"city": "", "country": ""}
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 10, "addressdetails": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        if resp.status_code == 200:
            addr = resp.json().get("address", {})
            city = (
                addr.get("city") or addr.get("town") or addr.get("village")
                or addr.get("municipality") or addr.get("county") or ""
            )
            result = {"city": city, "country": addr.get("country", "")}
    except requests.RequestException as e:
        print(f"  [geocode] failed for {lat},{lon}: {e}", file=sys.stderr)
    finally:
        time.sleep(NOMINATIM_DELAY_S)
    _geocode_cache[key] = result
    return result


def build_review_rows(clusters, geocode=True):
    rows = []
    for c in clusters:
        tags = c["tags"]
        name = tags.get("name") or f"Unnamed chess feature ({c['osm_type']}/{c['osm_id']})"
        city, country = "", ""
        if geocode:
            geo = reverse_geocode(c["lat"], c["lon"])
            city, country = geo["city"], geo["country"]

        source_bits = sorted(c["matched_by"])
        tag_summary = ", ".join(f"{k}={v}" for k, v in sorted(tags.items()))
        note = (
            f"[DRAFT — confirm via photo/Street View before publishing] "
            f"Found via OSM {'/'.join(source_bits)} match. Tags: {tag_summary or '(none)'}."
        )

        osm_link = f"https://www.openstreetmap.org/{c['osm_type']}/{c['osm_id']}"
        gmap_link = f"https://www.google.com/maps?q={c['lat']},{c['lon']}"

        rows.append(
            {
                "name": name,
                "labels": "chess board",
                "city": city,
                "coordinates": f"{c['lat']}, {c['lon']}",
                "note": note,
                "gmap": gmap_link,
                "link": "",
                "image": "",
                "days": "",
                "id": "",
                "_country": country,
                "_osm_link": osm_link,
                "_matched_by": "+".join(source_bits),
                "_cluster_size": c["cluster_size"],
                "_cluster_osm_refs": ";".join(c["cluster_osm_refs"]),
                "_raw_tags": json.dumps(tags, ensure_ascii=False),
                "_possible_duplicate_of": c["possible_duplicate_of"],
                "_duplicate_distance_m": c["duplicate_distance_m"],
            }
        )
    return rows


CSV_FIELDS = [
    "name", "labels", "city", "coordinates", "note", "gmap", "link", "image", "days", "id",
    "_country", "_osm_link", "_matched_by", "_cluster_size", "_cluster_osm_refs",
    "_raw_tags", "_possible_duplicate_of", "_duplicate_distance_m",
]


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_pending_json(rows, path):
    """Mirror pending_venues.json's shape (labels as a list) so it can go through
    the same one-by-one review flow described in CLAUDE.md, just from its own file
    so it doesn't get mixed into the scout agent's separate 292-entry queue."""
    pending = []
    for r in rows:
        pending.append(
            {
                "name": r["name"],
                "city": r["city"],
                "labels": [r["labels"]],
                "coordinates": r["coordinates"],
                "note": r["note"],
                "gmap": r["gmap"],
                "link": r["link"],
                "image": r["image"],
                "days": r["days"],
                "_source": "osm-overpass",
                "_country": r["_country"],
                "_osm_link": r["_osm_link"],
                "_matched_by": r["_matched_by"],
                "_possible_duplicate_of": r["_possible_duplicate_of"],
            }
        )
    path.write_text(json.dumps(pending, indent=2, ensure_ascii=False), encoding="utf-8")


def print_summary(raw_counts, merged_count, clustered, rows):
    print("\n=== Giant Chessboard Finder summary ===")
    for label, count in raw_counts.items():
        print(f"  raw hits [{label}]: {count}")
    print(f"  after id-level de-dup (both queries merged): {merged_count}")
    print(f"  after {DEDUPE_RADIUS_M}m spatial clustering: {len(clustered)}")

    both = sum(1 for c in clustered if c["matched_by"] == {"tagged", "freetext"})
    tag_only = sum(1 for c in clustered if c["matched_by"] == {"tagged"})
    text_only = sum(1 for c in clustered if c["matched_by"] == {"freetext"})
    print(f"    tag-only: {tag_only}, freetext-only: {text_only}, both: {both}")

    dupes = sum(1 for r in rows if r["_possible_duplicate_of"])
    print(f"  flagged as possibly already in the directory: {dupes}")
    print(f"  net new candidates for review: {len(rows) - dupes}")

    if any(r["city"] or r["_country"] for r in rows):
        from collections import Counter

        city_counts = Counter(f"{r['city']}, {r['_country']}".strip(", ") for r in rows if r["city"] or r["_country"])
        print("\n  top cities by hit count:")
        for city, n in city_counts.most_common(15):
            print(f"    {n:3d}  {city or '(unknown)'}")

        country_counts = Counter(r["_country"] for r in rows if r["_country"])
        print("\n  top countries by hit count:")
        for country, n in country_counts.most_common(15):
            print(f"    {n:3d}  {country}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", default=str(REPO_ROOT), help="Where to write the review CSV/JSON (default: repo root)")
    parser.add_argument("--skip-geocode", action="store_true", help="Skip Nominatim reverse geocoding (faster, no city/country)")
    parser.add_argument("--dedupe-radius-m", type=float, default=DEDUPE_RADIUS_M)
    parser.add_argument("--existing-radius-m", type=float, default=EXISTING_MATCH_RADIUS_M)
    parser.add_argument("--tagged-json", help="(offline/testing) read raw Overpass elements for the tag query from this JSON file instead of hitting the live API")
    parser.add_argument("--freetext-json", help="(offline/testing) same, for the free-text query")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_counts = {}
    all_candidates = []
    overrides = {"tagged": args.tagged_json, "freetext": args.freetext_json}
    for label, query in QUERIES:
        override_path = overrides.get(label)
        if override_path:
            elements = json.loads(Path(override_path).read_text(encoding="utf-8"))
        else:
            print(f"Querying Overpass [{label}]...")
            elements = run_overpass_query(query, label)
        raw_counts[label] = len(elements)
        all_candidates.extend(elements_to_candidates(elements, label))

    merged = merge_by_osm_id(all_candidates)
    clustered = spatial_dedupe(merged, radius_m=args.dedupe_radius_m)

    existing_venues = load_existing_venues()
    flag_possible_duplicates(clustered, existing_venues, radius_m=args.existing_radius_m)

    if not args.skip_geocode:
        print(f"Reverse-geocoding {len(clustered)} clusters via Nominatim (~{NOMINATIM_DELAY_S}s each)...")
    rows = build_review_rows(clustered, geocode=not args.skip_geocode)

    csv_path = out_dir / "giant_chessboards_review.csv"
    json_path = out_dir / "pending_giant_chessboards.json"
    write_csv(rows, csv_path)
    write_pending_json(rows, json_path)

    print_summary(raw_counts, len(merged), clustered, rows)
    print(f"\nWrote {len(rows)} candidates to:\n  {csv_path}\n  {json_path}")


if __name__ == "__main__":
    main()
