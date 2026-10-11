import copy
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import quote_plus
import naver_cafe as n
import watch as w
from test_watch import event, NOW, CFG


class CafeTests(unittest.TestCase):
    def test_html_is_escaped_and_unknown_time_not_invented(self):
        value = n.article(event(title='<script>bad</script>', artists=' ', tickets=[{'name': 'bad', 'url': 'javascript:alert(1)'}]))
        self.assertNotIn('<script>', value['content'])
        self.assertNotIn('javascript:', value['content'])
        self.assertIn('공식 예매처에서 확인', value['content'])
        self.assertIn(n.ATTRIBUTION, value['content'])
        named = n.article(event(tickets=[{'name': 'NOL', 'url': 'https://example.com/ticket'}]))
        self.assertIn('NOL', named['content'])
        self.assertNotIn('href=', named['content'])
        self.assertNotIn('https://example.com', named['content'])

    def test_multipart_utf8_fields_and_image(self):
        draft = n.article(event())
        body, kind = n.multipart(draft, ('poster.jpg', 'image/jpeg', b'\xff\xd8\xfftest'))
        self.assertIn(quote_plus(draft['subject']).encode(), body)
        self.assertIn(b'name="image"', body)
        self.assertIn(b'\xff\xd8\xfftest', body)
        self.assertIn('multipart/form-data', kind)

    def test_poster_rejects_arbitrary_hosts_and_html(self):
        with self.assertRaises(n.CafeError):
            n.poster_bytes('https://127.0.0.1/private')
        with patch.object(n, 'transport', return_value=b'<html>bad</html>'):
            with self.assertRaises(n.CafeError):
                n.poster_bytes('http://www.kopis.or.kr/upload/a.jpg')

    def test_article_created_once_and_retry_uses_saved_link(self):
        state = {'events': {}}
        calls, saves = [], []
        def create(draft, poster, token, config):
            self.assertEqual(state['cafe_pending']['event_id'], 'kopis:PF999999')
            calls.append(draft)
            return {'article_id': '1', 'url': 'https://cafe.naver.com/f-e/cafes/31702916/articles/1', 'announced': False}
        for _ in range(2):
            events = [event()]
            n.ensure_articles(events, state, {'club_id': '31702916', 'menu_id': '36'}, NOW,
                              lambda: saves.append(copy.deepcopy(state)), get_token=lambda: 'fake',
                              load_poster=lambda _: None, create=create)
            self.assertTrue(events[0]['cafe_unannounced'])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(saves), 2)
        self.assertIsNone(state['cafe_pending'])

    def test_uncertain_cafe_post_stops_retry(self):
        state = {}
        def fail(*args):
            raise n.CafeError('timeout')
        def run():
            n.ensure_articles([event()], state, {}, NOW, lambda: None,
                              get_token=lambda: 'fake', load_poster=lambda _: None, create=fail)
        with self.assertRaises(n.CafeError):
            run()
        with self.assertRaises(n.CafeError):
            run()
        self.assertIsNotNone(state['cafe_pending'])

    def test_failed_checkpoint_prevents_cafe_post(self):
        def fail():
            raise w.SafeError('push failed')
        with patch.object(n, 'publish') as create:
            with self.assertRaises(w.SafeError):
                n.ensure_articles([event()], {}, {}, NOW, fail, get_token=lambda: 'fake',
                                  load_poster=lambda _: None, create=create)
            create.assert_not_called()

    def test_discord_summary_acknowledges_existing_article(self):
        e = event(cafe_url='https://cafe.naver.com/f-e/cafes/31702916/articles/1', cafe_unannounced=True)
        previous = w.next_snapshot(e, None, NOW, True)
        state = {'events': {e['id']: previous}, 'pending': None,
                 'cafe_articles': {e['id']: {'url': e['cafe_url'], 'announced': False}}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(w, 'webhook_url', return_value='unused'):
            captured = []
            def send(url, payload):
                captured.append(payload)
                return b'{"id":"2"}'
            w.deliver([e], state, CFG, NOW, Path(tmp) / 'state.json', send=send)
        self.assertIn(e['cafe_url'], captured[0]['content'])
        self.assertIn(n.ATTRIBUTION, captured[0]['content'])
        self.assertTrue(state['cafe_articles'][e['id']]['announced'])

    def test_nested_naver_success_uses_fixed_target_link(self):
        response = {'message': {'status': '200', 'result': {'articleId': 123, 'articleUrl': 'https://unexpected.example/'}}}
        with patch.object(n, 'transport', return_value=json.dumps(response).encode()):
            result = n.publish(n.article(event()), None, 'fake', {'club_id': '31702916', 'menu_id': '36'})
        self.assertEqual(result['url'], 'https://cafe.naver.com/f-e/cafes/31702916/articles/123')


if __name__ == '__main__':
    unittest.main()
