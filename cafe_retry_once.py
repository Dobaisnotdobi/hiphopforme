"""Explicit manual retry of the single previously rejected concert."""
import os
import json
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement
import watch as w
import naver_cafe as n


def main():
    state_path = w.ROOT / 'data/state.json'
    state = w.read_json(state_path)
    target = 'kopis:PF301281'
    pending = state.get('cafe_pending')
    if state.get('pending') or not pending or pending.get('event_id') != target:
        raise n.CafeError('Expected rejected attempt is not pending; no post sent.')
    if target in state.get('cafe_articles', {}):
        raise n.CafeError('Article already recorded; no post sent.')
    original_api = w.api
    def selected_api(path, key, **params):
        if path == 'pblprfr':
            row = Element('db')
            SubElement(row, 'genrenm').text = '대중음악'
            SubElement(row, 'mt20id').text = 'PF301281'
            return [row]
        if path != 'pblprfr/PF301281':
            raise n.CafeError('Unexpected concert requested')
        return original_api(path, key, **params)
    w.api = selected_api
    now = datetime.now(w.KST)
    config = w.read_json(w.ROOT / 'config.json')
    events, _ = w.prepare(w.collect({**config, 'lookahead_days': 0}, now), config, now)
    events = [e for e in events if e['id'] == target and e['eligible']]
    if len(events) != 1:
        raise n.CafeError('Concert no longer eligible; no post sent.')
    state['cafe_previous_attempt'] = pending
    state['cafe_pending'] = None
    def publish_approved(draft, poster, token, config):
        approved = {'subject': '[10.17 · 서울] 디핵 — 디핵과 별빛 연맹 1.5',
                    'content': (w.ROOT / 'data/dhack-approved.html').read_text(encoding='utf-8')}
        club, menu = str(config['club_id']), str(config['menu_id'])
        if (club, menu) != ('31702916', '36'):
            raise n.CafeError('Unexpected approved destination')
        if not poster:
            raise n.CafeError('Poster attachment missing; no post sent.')
        body, content_type = n.multipart(approved, poster)
        result = json.loads(n.transport(
            f'https://openapi.naver.com/v1/cafe/{club}/menu/{menu}/articles',
            body, {'Authorization': 'Bearer ' + token, 'Content-Type': content_type}))
        message = result.get('message', result)
        value = message.get('result', message)
        article_id = str(value.get('articleId', ''))
        if str(message.get('status')) != '200' or not article_id.isdigit():
            raise n.CafeError('Creation not confirmed; inspect pending before retry.')
        return {'article_id': article_id,
                'url': f'https://cafe.naver.com/f-e/cafes/{club}/articles/{article_id}',
                'announced': False}
    n.ensure_articles(events, state, w.read_json(w.ROOT / 'naver.json'), now,
                      lambda: w.checkpoint(state_path, state, True),
                      load_poster=n.poster_bytes, create=publish_approved)
    print('Cafe article created:', state['cafe_articles'][target]['url'])


if __name__ == '__main__':
    try:
        main()
    except (n.CafeError, w.SafeError) as exc:
        raise SystemExit(str(exc))
    except Exception:
        raise SystemExit('Unexpected failure; details suppressed.')
