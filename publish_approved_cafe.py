"""User-approved eight-article batch. Cafe only; durable checkpoints prevent repeats."""
from datetime import datetime
import watch as w
import naver_cafe as n

def main():
    now = datetime.now(w.KST)
    if now.date().isoformat() != '2026-10-21':
        raise w.SafeError('Approval snapshot expired; no posts sent.')
    state_path = w.ROOT / 'data/state.json'
    state = w.read_json(state_path)
    if state.get('pending') or state.get('cafe_pending'):
        raise w.SafeError('Unresolved delivery exists; no posts sent.')
    config = w.read_json(w.ROOT / 'naver.json')
    if config != {'club_id': '31702916', 'menu_id': '36'}:
        raise w.SafeError('Unexpected destination; no posts sent.')
    events = w.read_json(w.ROOT / 'data/cafe-approved-20261021.json')
    if len(events) != 8 or len({e['id'] for e in events}) != 8:
        raise w.SafeError('Invalid approved batch')
    # Member-authored duplicate verified directly against title, date and venue.
    state.setdefault('cafe_articles', {}).setdefault('kopis:PF303858', {
        'article_id': '5581', 'url': 'https://cafe.naver.com/hshcompany/5581',
        'announced': True, 'existing_member_post': True})
    persist = lambda: w.checkpoint(state_path, state, True)
    persist()
    n.article = lambda event: event['approved_draft']
    def require_poster(url):
        poster = n.poster_bytes(url)
        if not poster:
            raise n.CafeError('Required poster missing; no post sent.')
        return poster
    def create(draft, poster, token, target):
        result = n.publish(draft, poster, token, target)
        print('Created: ' + result['url'], flush=True)
        return result
    n.ensure_articles(events, state, config, now, persist,
                      load_poster=require_poster, create=create)
    print('Approved batch complete; eight articles recorded. No Discord sent.', flush=True)

if __name__ == '__main__':
    try:
        main()
    except (w.SafeError, n.CafeError) as exc:
        raise SystemExit(str(exc))
    except Exception:
        raise SystemExit('Unexpected failure; inspect pending state before any retry.')
