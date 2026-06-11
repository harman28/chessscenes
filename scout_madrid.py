import scout, anthropic, json
from pathlib import Path
client = anthropic.Anthropic()
existing = scout.load_existing()
skip = existing.get('madrid', set())
print('Scouting Madrid...')
results = scout.scout_city(client, 'Madrid', skip)
pending = scout.load_pending()
for v in results:
    v['city'] = 'Madrid'
    v['_scouted'] = '2026-06-11'
    pending.append(v)
Path('pending_venues.json').write_text(json.dumps(pending, indent=2, ensure_ascii=False))
print(f'Added {len(results)} Madrid venues to pending')
