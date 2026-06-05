#!/usr/bin/env python3
"""
Scout agent for chessscenes.com.
Searches the web for chess venues in rotating cities and appends candidates
to pending_venues.json for Harman's review.

Run daily via GitHub Actions. Requires ANTHROPIC_API_KEY env var.
"""

import anthropic
import csv
import json
import re
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent
CSV_PATH = REPO_ROOT / "Chess Scenes (Public) - chess_scenes_venues.csv"
PENDING_PATH = REPO_ROOT / "pending_venues.json"

# Cities not yet well-covered, rotating through 3 per day
CITIES = [
    "Vienna", "Warsaw", "Lisbon", "Madrid", "Rome", "Milan", "Naples",
    "Bratislava", "Zagreb", "Ljubljana", "Tallinn", "Vilnius",
    "Sofia", "Thessaloniki", "Valletta", "Nicosia",
    "San Francisco", "Los Angeles", "Seattle", "Boston", "Washington DC",
    "Portland", "Denver", "Austin", "Nashville", "New Orleans",
    "Montreal", "Vancouver", "Calgary", "Ottawa",
    "São Paulo", "Rio de Janeiro", "Buenos Aires", "Bogotá", "Medellín", "Lima",
    "Cairo", "Nairobi", "Lagos", "Johannesburg", "Accra",
    "Bangkok", "Hanoi", "Ho Chi Minh City", "Kuala Lumpur", "Jakarta",
    "Manila", "Taipei", "Hong Kong", "Osaka",
    "Dubai", "Tel Aviv", "Istanbul", "Beirut", "Amman",
    "Melbourne", "Brisbane", "Perth", "Auckland", "Wellington",
    "Kyiv", "Tbilisi", "Yerevan", "Baku",
    "Tunis", "Casablanca", "Algiers",
]


def load_existing():
    """Return dict of city_lower -> set of name_lower already in CSV."""
    existing = {}
    if CSV_PATH.exists():
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                city = row["city"].strip().lower()
                name = row["name"].strip().lower()
                existing.setdefault(city, set()).add(name)
    return existing


def load_pending():
    if PENDING_PATH.exists():
        return json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    return []


def cities_for_today():
    """Pick 3 cities to scout today by rotating through the list."""
    day_index = (date.today() - date(2026, 1, 1)).days % len(CITIES)
    return [CITIES[(day_index + i) % len(CITIES)] for i in range(3)]


def extract_json_array(text):
    """Pull the first JSON array out of a blob of text."""
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return []


def scout_city(client, city, skip_names):
    """
    Run a web-search agent for one city.
    Returns a list of venue dicts (may be empty).
    """
    skip_str = ", ".join(list(skip_names)[:30]) if skip_names else "none"

    messages = [
        {
            "role": "user",
            "content": (
                f"Search the web for places to play chess in {city}. "
                f"Try queries like: 'chess club {city}', 'chess meetup {city}', "
                f"'chess bar {city}', 'where to play chess {city}'.\n\n"
                f"For each venue you find, extract a JSON object with these fields:\n"
                f"- name (string)\n"
                f"- city: \"{city}\"\n"
                f"- labels: one or more of: chess club, chess bar, chess meetup, "
                f"chess board, chess shop, chess museum, chess memorial\n"
                f"- coordinates: \"lat, lng\" as a string\n"
                f"- note: 1–2 sentences — what it is and when chess happens\n"
                f"- gmap: Google Maps URL if found, else empty string\n"
                f"- link: website or Instagram URL if found, else empty string\n"
                f"- image: leave as empty string\n"
                f"- days: comma-separated day names if chess happens on specific days "
                f"(e.g. \"Tuesday\" or \"Monday, Wednesday\"), empty string if always open or unknown\n\n"
                f"Skip these already-known venues: {skip_str}\n\n"
                f"When you have finished searching, return ONLY a valid JSON array of found venues. "
                f"If you find nothing new, return []."
            ),
        }
    ]

    # Agentic loop — keep going until the model stops using tools
    while True:
        response = client.beta.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages,
            betas=["web-search-2025-03-05"],
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            text = "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
            return extract_json_array(text)

        # Tool use — acknowledge so the loop continues
        tool_results = [
            {"type": "tool_result", "tool_use_id": block.id, "content": ""}
            for block in response.content
            if block.type == "tool_use"
        ]
        if tool_results:
            messages.append({"role": "user", "content": tool_results})


def main():
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    existing = load_existing()
    pending = load_pending()
    pending_keys = {(v["name"].lower(), v["city"].lower()) for v in pending}

    target_cities = cities_for_today()
    print(f"Scouting today: {', '.join(target_cities)}")

    new_count = 0
    for city in target_cities:
        print(f"\n--- {city} ---")
        skip = existing.get(city.lower(), set())

        try:
            candidates = scout_city(client, city, skip)
        except Exception as e:
            print(f"  Error: {e}")
            continue

        for venue in candidates:
            name = venue.get("name", "").strip()
            if not name:
                continue
            key = (name.lower(), city.lower())
            if key in pending_keys or name.lower() in existing.get(city.lower(), set()):
                print(f"  Skip (duplicate): {name}")
                continue

            venue["city"] = city
            venue["_scouted"] = date.today().isoformat()
            pending.append(venue)
            pending_keys.add(key)
            new_count += 1
            print(f"  + {name}")

    PENDING_PATH.write_text(
        json.dumps(pending, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n{new_count} new candidate(s) added. Total pending: {len(pending)}")


if __name__ == "__main__":
    main()
