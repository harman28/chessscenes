#!/usr/bin/env python3
"""
Barblitz scraper for chessscenes.com.

Hand-written HTML parser — no LLM, no anthropic dependency, no per-run cost. barblitz.co
has a stable tournament grid with real structured data (ISO datetimes, explicit venue/city
text), so there's nothing here that needs a web-search agent to extract.

Run periodically via GitHub Actions (see .github/workflows/barblitz_scraper.yml). If
barblitz.co changes its markup and the .tc-card selectors stop matching, this raises
instead of silently writing an empty result — that fails the GitHub Actions step, and
GitHub's default failure-notification email is the alert that it's time to come update
the selectors (or, if barblitz.co ever ships a real API, switch to that instead).

Candidates are written to pending_events.json for one-by-one conversational review, same
as pending_venues.json (see CLAUDE.md). Barblitz's schedule is genuinely one-off/roaming —
each tournament needs its own dated entry, there is no recurring "every Wednesday" to seed
once and forget.
"""

import csv
import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).parent
CSV_PATH = REPO_ROOT / "Chess Scenes (Public) - chess_scenes_venues.csv"
PENDING_PATH = REPO_ROOT / "pending_events.json"

BARBLITZ_URL = "https://barblitz.co/"
USER_AGENT = "ChessScenes/1.0 (+https://chessscenes.com)"
MIN_EXPECTED_CARDS = 3  # if barblitz.co's markup changes, this should trip well before hitting 0


def _normalize(name):
    name = name.lower()
    name = re.sub(r"\b(cafe|café|de|het|the|'t)\b", " ", name)
    return re.sub(r"[^a-z0-9]+", "", name)


def load_places():
    """(normalized_name, slug) pairs for fuzzy-matching a scraped venue name to a known place."""
    if not CSV_PATH.exists():
        return []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return [(_normalize(row["name"]), row["slug"]) for row in csv.DictReader(f)]


def match_place(venue_name, places):
    if not venue_name:
        return None
    norm = _normalize(venue_name)
    if len(norm) < 4:
        return None
    for place_norm, slug in places:
        if len(place_norm) < 4:
            continue
        if norm in place_norm or place_norm in norm:
            return slug
    return None


def load_pending():
    if PENDING_PATH.exists():
        return json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    return []


def scrape(html):
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("a.tc-card")
    if len(cards) < MIN_EXPECTED_CARDS:
        raise RuntimeError(
            f"Only found {len(cards)} .tc-card element(s) on {BARBLITZ_URL} — expected "
            f"at least {MIN_EXPECTED_CARDS}. barblitz.co's markup may have changed; the "
            f".tc-card selectors in this script need updating."
        )

    places = load_places()
    results = []
    for card in cards:
        href = card.get("href", "")
        m = re.search(r"/tournament/(\d+)/", href)
        tournament_id = m.group(1) if m else None

        title_el = card.select_one(".tc-card-title")
        title = title_el.get_text(strip=True) if title_el else None

        time_el = card.select_one("time[datetime]")
        if not time_el or not title or not tournament_id:
            continue  # skip anything we can't get a date/title/id for — better to miss one than guess

        specific_date = time_el["datetime"][:10]
        local_time = time_el.get("data-event-time")

        venue_name, city = None, None
        marker_icon = card.select_one("i.fa-map-marker-alt")
        if marker_icon:
            row = marker_icon.find_parent("div")
            span = row.select_one("span.body-m") if row else None
            if span:
                text = span.get_text(strip=True)
                if "," in text:
                    venue_name, city = [p.strip() for p in text.rsplit(",", 1)]
                else:
                    venue_name = text

        place_slug = match_place(venue_name, places)

        results.append({
            "_barblitz_tournament_id": tournament_id,
            "_barblitz_url": f"https://barblitz.co/tournament/{tournament_id}/",
            "place_slug": place_slug,
            "standalone_name": None if place_slug else venue_name,
            "standalone_city": None if place_slug else city,
            "community": "BarBlitz",
            "title": "BarBlitz",  # the scraped title (e.g. "Blitz Wednesday - De Laurierboom")
                                  # is just barblitz.co's own per-tournament copy — the venue
                                  # and date are already carried separately (place_slug/
                                  # standalone_name, specific_date), so displaying it verbatim
                                  # only duplicated that instead of adding anything.
            "time": local_time,
            "specific_date": specific_date,
            "external_link": f"https://barblitz.co/tournament/{tournament_id}/",
            "active": True,
        })
    return results


def main():
    resp = requests.get(BARBLITZ_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
    resp.raise_for_status()
    scraped = scrape(resp.text)

    pending = load_pending()
    pending_ids = {e.get("_barblitz_tournament_id") for e in pending}

    new_count = 0
    for entry in scraped:
        if entry["_barblitz_tournament_id"] in pending_ids:
            continue
        pending.append(entry)
        pending_ids.add(entry["_barblitz_tournament_id"])
        new_count += 1
        where = entry["place_slug"] or f"(standalone: {entry['standalone_name']!r}, needs coords)"
        print(f"  + {entry['title']} ({entry['specific_date']}) -> {where}")

    PENDING_PATH.write_text(json.dumps(pending, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{new_count} new Barblitz tournament(s) added. Total pending: {len(pending)}")


if __name__ == "__main__":
    main()
