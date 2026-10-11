import copy
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import watch as w

NOW = datetime.fromisoformat('2026-10-11T09:17:00+09:00')
CFG = w.read_json(w.ROOT / 'config.json')


def event(**kwargs):
    return dict({'id': 'kopis:PF999999', 'title': '테스트 힙합 공연',
                 'venue': '가상 공연장', 'region': '서울특별시', 'start': '2026-11-01',
                 'end': '2026-11-01', 'artists': '테스트', 'prices': [99000],
                 'status': '공연예정', 'url': 'https://example.org/test',
                 'ticket_open_at': None, 'eligible': True}, **kwargs)


class WatchTests(unittest.TestCase):
    def test_prices_and_conditional_discounts(self):
        self.assertEqual(w.prices('VIP석 150,000원, S석 99,000원'), [99000, 150000])
        self.assertEqual(w.prices('전석 무료'), [0])
        for text in ['학생 할인 50,000원', '회원 10,000원', '미정', '50,000~110,000원']:
            self.assertEqual(w.prices(text), [])

    def test_boundary_budget_and_regions(self):
        for price, yes in [(100000, True), (100001, False), (0, True)]:
            rows, _ = w.prepare([event(prices=[price])], CFG, NOW)
            self.assertEqual(rows[0]['eligible'], yes)
        self.assertFalse(w.prepare([event(region='경기도')], CFG, NOW)[0])
        self.assertTrue(w.prepare([event(region='인천광역시')], CFG, NOW)[0])

    def test_ended_same_day_and_cancelled(self):
        for item in [event(end='2026-10-10'), event(end='2026-10-11'), event(status='공연취소')]:
            self.assertFalse(w.prepare([item], CFG, NOW)[0])

    def test_artist_boundary(self):
        self.assertFalse(w.has_term('Melody show', 'ELO'))
        self.assertTrue(w.has_term('ELO concert', 'ELO'))

    def test_duplicate_id_and_identity(self):
        first = event()
        second = event(id='notice:other', title='테스트  힙합 공연')
        rows, _ = w.prepare([first, copy.deepcopy(first), second], CFG, NOW)
        self.assertEqual(len(rows), 1)

    def test_new_then_no_repeat(self):
        e = event()
        self.assertEqual(w.changes(e, None, NOW, 100000), ['신규 공연'])
        snap = w.next_snapshot(e, None, NOW, True)
        self.assertEqual(w.changes(e, snap, NOW, 100000), [])

    def test_price_change_and_return(self):
        old = w.next_snapshot(event(prices=[90000]), None, NOW, True)
        self.assertIn('가격 변경', w.changes(event(), old, NOW, 100000)[0])
        high = event(prices=[120000], eligible=False)
        self.assertEqual(w.changes(high, old, NOW, 100000), [])
        high_snap = w.next_snapshot(high, old, NOW, False)
        self.assertIn('가격 변경', w.changes(event(), high_snap, NOW, 100000)[0])

    def test_missing_price_does_not_erase_baseline(self):
        old = w.next_snapshot(event(), None, NOW, True)
        snap = w.next_snapshot(event(prices=[], eligible=False), old, NOW, False)
        self.assertEqual(snap['prices'], [99000])

    def test_ticket_announcement_then_open(self):
        e = event(ticket_open_at='2026-10-12T10:00:00+09:00')
        self.assertIn('티켓 오픈 예정', w.changes(e, None, NOW, 100000))
        snap = w.next_snapshot(e, None, NOW, True)
        self.assertEqual(w.changes(e, snap, NOW, 100000), [])
        later = datetime.fromisoformat('2026-10-13T10:00:00+09:00')
        self.assertEqual(w.changes(e, snap, later, 100000), ['티켓 오픈'])
        snap = w.next_snapshot(e, snap, later, True)
        self.assertEqual(w.changes(e, snap, later, 100000), [])

    def test_unknown_open_is_not_inferred(self):
        self.assertEqual(w.changes(event(), None, NOW, 100000), ['신규 공연'])
        with self.assertRaises(w.SafeError):
            w.parse_time('2026-10-12T10:00:00')

    def test_expired_override_ignored(self):
        stale = {'verified': True, 'valid_until': '2026-10-10'}
        self.assertEqual(w.merge_verified([event()], [stale], NOW), [event()])

    def test_mentions_and_length(self):
        payload = w.message(event(title='@everyone' * 1000), ['신규 공연'], NOW)
        self.assertEqual(payload['allowed_mentions'], {'parse': []})
        self.assertNotIn('@everyone', payload['content'])
        self.assertLessEqual(len(payload['content']), 1950)

    def test_requested_format_has_no_metadata_or_links(self):
        e = event(artists=' ', title='D-Hack 콘서트', runtime='120분')
        text = w.message(e, ['신규 공연'], NOW, CFG)['content']
        self.assertEqual([line.split(': ')[0] for line in text.splitlines()],
                         ['공연명', '아티스트', '일자', '장소', '설명'])
        self.assertIn('아티스트: D-Hack', text)
        self.assertIn('120분', text)
        for forbidden in ('https://', '확인:', '출처:', '알림 ID:'):
            self.assertNotIn(forbidden, text)

    def test_multiple_concerts_one_request_and_all_saved(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(w, 'webhook_url', return_value='unused'):
            state = {'version': 1, 'events': {}, 'pending': None}
            path = Path(tmp) / 'state.json'
            events = [event(id=f'event:{i}', title=f'공연{i}') for i in range(3)]
            calls = []
            def send(url, payload):
                pending = w.read_json(path)['pending']
                self.assertEqual(len(pending['event_ids']), 3)
                self.assertEqual(state['events'], {})
                calls.append(payload)
                return b'{"id":"123"}'
            self.assertEqual(w.deliver(events, state, CFG, NOW, path, send=send), 3)
            self.assertEqual(len(calls), 1)
            for i in range(3):
                self.assertIn(f'공연{i}', calls[0]['content'])
                self.assertTrue(state['events'][f'event:{i}']['notified'])
            self.assertEqual(w.deliver(events, state, CFG, NOW, path, send=send), 0)
            self.assertEqual(len(calls), 1)
            self.assertEqual(state['last_delivery']['message_id'], '123')

    def test_long_batch_one_attachment_without_dropping_events(self):
        planned = [(event(id=str(i), title=f'공연{i} ' + '가' * 190), ['신규 공연']) for i in range(30)]
        payload = w.batch_message(planned, NOW, CFG)
        self.assertLessEqual(len(payload['content']), 2000)
        self.assertIn('공연29', payload['_attachment_text'])
        data, content_type = w.encode_payload(payload)
        self.assertIn('multipart/form-data', content_type)
        self.assertIn('공연29'.encode(), data)
        self.assertIn(b'filename="concerts.txt"', data)
        self.assertIn(b'"allowed_mentions": {"parse": []}', data)

    def test_failed_batch_keeps_all_pending_and_none_delivered(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(w, 'webhook_url', return_value='unused'):
            state = {'version': 1, 'events': {}, 'pending': None}
            path = Path(tmp) / 'state.json'
            events = [event(id='a'), event(id='b')]
            def fail(url, payload):
                raise w.SafeError('timeout')
            with self.assertRaises(w.SafeError):
                w.deliver(events, state, CFG, NOW, path, send=fail)
            persisted = w.read_json(path)
            self.assertEqual(persisted['events'], {})
            self.assertEqual(set(persisted['pending']['snapshots']), {'a', 'b'})

    def test_webhook_validation(self):
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://evil.example/api/webhooks/1/a'}):
            with self.assertRaises(w.SafeError):
                w.webhook_url()

    def test_success_saved_and_repeat_silent(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(w, 'webhook_url', return_value='unused'), patch.object(w.time, 'sleep'):
            state = {'version': 1, 'events': {}, 'pending': None}
            path = Path(tmp) / 'state.json'
            calls = []
            def send(url, payload):
                self.assertIsNotNone(w.read_json(path)['pending'])
                calls.append(payload)
                return b'{"id":"123"}'
            self.assertEqual(w.deliver([event()], state, CFG, NOW, path, send=send), 1)
            self.assertEqual(w.deliver([event()], state, CFG, NOW, path, send=send), 0)
            self.assertEqual(len(calls), 1)
            self.assertIsNone(w.read_json(path)['pending'])

    def test_uncertain_delivery_is_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(w, 'webhook_url', return_value='unused'):
            state = {'version': 1, 'events': {}, 'pending': None}
            path = Path(tmp) / 'state.json'
            def fail(url, payload):
                raise w.SafeError('timeout')
            with self.assertRaises(w.SafeError):
                w.deliver([event()], state, CFG, NOW, path, send=fail)
            loaded = w.read_json(path)
            self.assertIsNotNone(loaded['pending'])
            with self.assertRaises(w.SafeError):
                w.deliver([event()], loaded, CFG, NOW, path, send=fail)

    def test_checkpoint_failure_prevents_post(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(w, 'webhook_url', return_value='unused'), patch.object(w, 'checkpoint', side_effect=w.SafeError('push failed')):
            with patch.object(w, 'request') as send:
                with self.assertRaises(w.SafeError):
                    w.deliver([event()], {'events': {}, 'pending': None}, CFG, NOW,
                              Path(tmp) / 'state.json', send=send)
                send.assert_not_called()

    def test_collection_windows_pagination_and_deduplication(self):
        calls = []
        listing = w.ET.fromstring('<db><mt20id>PF999999</mt20id><genrenm>대중음악</genrenm></db>')
        detail = w.ET.fromstring('<db><prfnm>힙합 테스트</prfnm><prfpdfrom>2026.11.01</prfpdfrom><prfpdto>2026.11.01</prfpdto><area>서울특별시</area><pcseguidance>전석 99,000원</pcseguidance></db>')
        def fake_api(path, key, **params):
            calls.append((path, params))
            if path != 'pblprfr':
                return [detail]
            start = datetime.strptime(params['stdate'], '%Y%m%d')
            end = datetime.strptime(params['eddate'], '%Y%m%d')
            self.assertLessEqual((end - start).days, 30)
            return [listing] * 100 if params['cpage'] == 1 else []
        with patch.dict(os.environ, {'KOPIS_API_KEY': 'fake'}), patch.object(w, 'api', side_effect=fake_api), patch.object(w.time, 'sleep'):
            rows = w.collect(CFG, NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['prices'], [99000])
        self.assertEqual(sum(path != 'pblprfr' for path, _ in calls), 1)
        self.assertEqual({p['signgucode'] for path, p in calls if path == 'pblprfr'}, {'11', '28'})

    def test_api_error_is_not_empty_success(self):
        with patch.object(w, 'request', return_value=b'<error>invalid key</error>'):
            with self.assertRaises(w.SafeError):
                w.api('pblprfr', 'fake-secret')

    def test_network_exception_does_not_leak_secret(self):
        with patch.object(w, 'build_opener') as opener:
            opener.return_value.open.side_effect = RuntimeError('https://host/?secret=do-not-leak')
            with self.assertRaises(w.SafeError) as ctx:
                w.request('https://host/?secret=do-not-leak')
        self.assertNotIn('do-not-leak', str(ctx.exception))

    def test_transient_get_400_retried_but_post_not_retried(self):
        from unittest.mock import MagicMock
        error = w.HTTPError('https://example.org', 400, 'Bad Request', {}, None)
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'ok'
        with patch.object(w, 'build_opener') as opener, patch.object(w.time, 'sleep'):
            opener.return_value.open.side_effect = [error, response]
            self.assertEqual(w.request('https://example.org'), b'ok')
            self.assertEqual(opener.return_value.open.call_count, 2)
        with patch.object(w, 'build_opener') as opener, patch.object(w.time, 'sleep'):
            opener.return_value.open.side_effect = error
            with self.assertRaises(w.SafeError):
                w.request('https://example.org', {'content': 'test'})
            self.assertEqual(opener.return_value.open.call_count, 1)

    def test_persistent_get_400_stops_after_four_attempts(self):
        with patch.object(w, 'build_opener') as opener, patch.object(w.time, 'sleep'):
            opener.return_value.open.side_effect = w.HTTPError('https://example.org', 400, 'Bad Request', {}, None)
            with self.assertRaises(w.SafeError):
                w.request('https://example.org')
            self.assertEqual(opener.return_value.open.call_count, 4)


if __name__ == '__main__':
    unittest.main()
