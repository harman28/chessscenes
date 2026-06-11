import scout, anthropic, json, sys
from pathlib import Path

city = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else input("City: ")
client = anthropic.Anthropic()
existing = scout.load_existing()
skip = existing.get(city.lower(), set())
print(f'Scouting {city}...')
results = scout.scout_city(client, city, skip)
pending = scout.load_pending()
seen = {(v["name"].lower(), v["city"].lower()) for v in pending}
added = 0
for v in results:
    key = (v.get("name", "").lower(), city.lower())
    if key not in seen:
        v['city'] = city
        v['_scouted'] = '2026-06-11'
        pending.append(v)
        seen.add(key)
        added += 1
Path('pending_venues.json').write_text(json.dumps(pending, indent=2, ensure_ascii=False))
print(f'Added {added} {city} venues to pending')
