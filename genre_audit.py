"""Read-only collection audit: no publishing credentials or state writes."""
from datetime import datetime
import watch as w

now = datetime.now(w.KST)
config = w.read_json(w.ROOT / 'config.json')
state = w.read_json(w.ROOT / 'data/state.json')
raw = w.merge_verified(w.collect(config, now), w.read_json(w.ROOT / 'data/verified.json'), now)
selected, rejected = w.prepare(raw, config, now)
reasons = {r['id']: r['reason'] for r in rejected}
kept = {e['id']: e for e in selected}
rows = []
for event in raw:
    text = event['title'] + ' ' + event.get('artists', '')
    rows.append({**event, 'decision': reasons.get(event['id'], 'selected'),
                 'matched_terms': [t for t in config['keywords'] + config['artists'] if w.has_term(text, t)],
                 'already_posted': event['id'] in state.get('cafe_articles', {}),
                 'changes': w.changes(kept[event['id']], state['events'].get(event['id']), now, config['max_price_krw']) if event['id'] in kept else []})
w.save_json(w.ROOT / 'genre-audit.json', {'checked_at': now.isoformat(), 'config': config, 'events': rows})
print(f'Audit collected {len(rows)} events; selected {len(selected)}. No posts or state changes.')
