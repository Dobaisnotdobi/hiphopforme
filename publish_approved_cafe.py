"""User-approved concert batch with durable checkpoints to prevent repeats."""
from datetime import datetime
import watch as w
import naver_cafe as n

def main():
    now = datetime.now(w.KST)
    if now.date().isoformat() != '2026-11-09':
        raise w.SafeError('Approval snapshot expired; no posts sent.')
    state_path = w.ROOT / 'data/state.json'
    state = w.read_json(state_path)
    if state.get('pending') or state.get('cafe_pending'):
        raise w.SafeError('Unresolved delivery exists; no posts sent.')
    config = w.read_json(w.ROOT / 'naver.json')
    if config != {'club_id': '31702916', 'menu_id': '36'}:
        raise w.SafeError('Unexpected destination; no posts sent.')
    events = w.read_json(w.ROOT / 'data/cafe-approved-20261109.json')
    if [e['id'] for e in events] != ['nol:26015801', 'kopis:PF305410', 'melon-notice:13186', 'melon-notice:13222']:
        raise w.SafeError('Invalid approved batch')
    persist = lambda: w.checkpoint(state_path, state, True)
    persist()
    n.article = lambda event: event['approved_draft']
    def require_poster(path):
        allowed = {'data/posters-20261109/skinny.gif': 'image/gif',
                   'data/posters-20261109/hhf.png': 'image/png',
                   'data/posters-20261109/mono.jpg': 'image/jpeg',
                   'data/posters-20261109/kaogaii.jpg': 'image/jpeg'}
        if path not in allowed:
            raise n.CafeError('Unapproved poster path.')
        data = (w.ROOT / path).read_bytes()
        if len(data) > 5_000_000 or not data.startswith((b'GIF8', b'\x89PNG', b'\xff\xd8\xff')):
            raise n.CafeError('Invalid poster attachment.')
        return (path.rsplit('/', 1)[-1], allowed[path], data)
    def create(draft, poster, token, target):
        result = n.publish(draft, poster, token, target)
        print('Created: ' + result['url'], flush=True)
        return result
    n.ensure_articles(events, state, config, now, persist,
                      load_poster=require_poster, create=create)
    print('Approved batch complete; four articles recorded. No Discord sent.', flush=True)

if __name__ == '__main__':
    try:
        main()
    except (w.SafeError, n.CafeError) as exc:
        raise SystemExit(str(exc))
    except Exception:
        raise SystemExit('Unexpected failure; inspect pending state before any retry.')
