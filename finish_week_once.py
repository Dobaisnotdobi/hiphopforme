"""Finish the known weekly run after an explicit consecutive-post rejection."""
import os
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement
import watch as w
import naver_cafe as n


def main():
    now = datetime.now(w.KST)
    state_path = w.ROOT / 'data/state.json'
    state = w.read_json(state_path)
    pending = state.get('cafe_pending')
    if state.get('pending') or not pending or pending.get('event_id') != 'kopis:PF301425':
        raise w.SafeError('Expected rejected run not found; stopped.')
    if state['cafe_articles'].get('kopis:PF301281', {}).get('article_id') != '5469' or state['cafe_articles'].get('kopis:PF300493', {}).get('article_id') != '5472':
        raise w.SafeError('Existing article records do not match; stopped.')
    w.webhook_url()
    ids = ['PF301281', 'PF300493', 'PF301425']
    original_api = w.api
    def selected_api(path, key, **params):
        if path == 'pblprfr':
            rows = []
            for event_id in ids:
                row = Element('db')
                SubElement(row, 'genrenm').text = '대중음악'
                SubElement(row, 'mt20id').text = event_id
                rows.append(row)
            return rows
        if path.removeprefix('pblprfr/') not in ids:
            raise w.SafeError('Unexpected event')
        return original_api(path, key, **params)
    w.api = selected_api
    config = w.read_json(w.ROOT / 'config.json')
    raw = w.collect({**config, 'lookahead_days': 0}, now)
    events, _ = w.prepare(w.merge_verified(raw, w.read_json(w.ROOT / 'data/verified.json'), now), config, now)
    state['cafe_last_rate_limited'] = pending
    state['cafe_pending'] = None
    persist = lambda: w.checkpoint(state_path, state, True)
    persist()
    n.ensure_articles(events, state, w.read_json(w.ROOT / 'naver.json'), now, persist)
    count = w.deliver(events, state, config, now, state_path, True)
    print(f'Delivered {count} concert updates in one Discord summary.')
    for event_id in ids:
        article = state['cafe_articles'].get('kopis:' + event_id)
        if article:
            print('Cafe article:', article['url'])


if __name__ == '__main__':
    try:
        main()
    except (w.SafeError, n.CafeError) as exc:
        raise SystemExit(str(exc))
    except Exception:
        raise SystemExit('Unexpected failure; details suppressed.')
