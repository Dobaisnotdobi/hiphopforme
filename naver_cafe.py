"""Official Naver Cafe adapter. No posting until ENABLE_NAVER=true."""
import html
import json
import os
import re
import uuid
from urllib.error import HTTPError
from urllib.parse import quote_plus, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

ATTRIBUTION = '본 안내는 (재)예술경영지원센터 공연예술통합전산망(KOPIS)에서 제공하는 정보를 활용해 작성되었습니다.'


class CafeError(Exception):
    pass


def safe_error_description(value, headers):
    if not isinstance(value, str):
        return 'Description unavailable'
    secrets = [os.environ.get(k, '') for k in ('NAVER_CLIENT_ID', 'NAVER_CLIENT_SECRET',
               'NAVER_REFRESH_TOKEN', 'KOPIS_API_KEY', 'DISCORD_WEBHOOK_URL')]
    bearer = (headers or {}).get('Authorization', '')
    secrets += [bearer, bearer.removeprefix('Bearer ')]
    for secret in sorted(filter(None, secrets), key=len, reverse=True):
        for variant in (secret, quote_plus(secret)):
            value = value.replace(variant, '[REDACTED]')
    value = re.sub(r'https?://\S+|[\w.+-]+@[\w.-]+', '[REDACTED]', value)
    value = re.sub(r'[A-Za-z0-9_+/=.%~-]{20,}', '[REDACTED]', value)
    return ' '.join(value.split())[:600]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise CafeError('Naver request redirect refused; no credentials logged.')


def transport(url, data=None, headers=None, limit=6_000_000):
    try:
        req = Request(url, data=data, headers=headers or {})
        with build_opener(NoRedirect).open(req, timeout=30) as response:
            body = response.read(limit + 1)
            if len(body) > limit:
                raise CafeError('Response exceeds allowed size.')
            return body
    except HTTPError as exc:
        code = 'unrecognized'
        description = 'Description unavailable'
        if urlsplit(url).hostname == 'openapi.naver.com':
            try:
                value = json.loads(exc.read(20000))
                message = value.get('message', {})
                error = message.get('error', {}) if isinstance(message, dict) else {}
                candidate = value.get('errorCode', value.get('error_code'))
                if candidate is None and isinstance(error, dict):
                    candidate = error.get('code')
                if isinstance(candidate, (str, int)) and re.fullmatch(r'[A-Z]{0,3}[0-9]{1,5}', str(candidate)):
                    code = str(candidate)
                detail = value.get('errorMessage', value.get('error_description'))
                if detail is None and isinstance(error, dict):
                    detail = error.get('msg', error.get('message'))
                description = safe_error_description(detail, headers)
            except Exception:
                pass
        raise CafeError(f'Naver/image HTTP {exc.code}; API code {code}; detail: {description}') from None
    except CafeError:
        raise
    except Exception:
        raise CafeError('Naver/image request failed; details suppressed.') from None


def access_token():
    names = ('NAVER_CLIENT_ID', 'NAVER_CLIENT_SECRET', 'NAVER_REFRESH_TOKEN')
    if any(not os.environ.get(n) for n in names):
        raise CafeError('Add NAVER_CLIENT_ID, NAVER_CLIENT_SECRET and NAVER_REFRESH_TOKEN to Actions Secrets.')
    data = urlencode({'grant_type': 'refresh_token', 'client_id': os.environ[names[0]],
                      'client_secret': os.environ[names[1]], 'refresh_token': os.environ[names[2]]}).encode()
    value = json.loads(transport('https://nid.naver.com/oauth2.0/token', data,
                                {'Content-Type': 'application/x-www-form-urlencoded'}))
    if not value.get('access_token') or value.get('error'):
        raise CafeError('Naver login refresh failed. Reconnect the posting account.')
    return value['access_token']


def safe_url(value):
    u = urlsplit(value)
    return value if u.scheme in ('https', 'http') and u.hostname and not u.username and not u.password else ''


def text_form(draft):
    # Naver's form endpoint requires UTF-8 URL encoding followed by
    # MS949 URL encoding (the first pass is ASCII). Multipart is separate.
    return urlencode({'subject': quote_plus(draft['subject'], encoding='utf-8'),
                      'content': quote_plus(draft['content'], encoding='utf-8'),
                      'openyn': 'false', 'searchopen': 'false', 'ccl': 'false'},
                     encoding='cp949').encode('ascii')


def article(event):
    esc = lambda v: html.escape(str(v), quote=True)
    date_text = event['start'] if event['start'] == event['end'] else event['start'] + ' ~ ' + event['end']
    title = f"[{event['start'][5:]} · {event['region']}] {event['title']} — {min(event['prices']):,}원부터"
    fields = [('아티스트', event.get('artists', '').strip() or '출연진 미공개'),
              ('공연 일자', date_text), ('공연 시간', event.get('schedule', '').strip() or '공식 예매처에서 확인'),
              ('장소', event['venue']), ('가격', event.get('price_text', '').strip() or
               ', '.join(f'{p:,}원' for p in event['prices']))]
    body = '<h2>' + esc(event['title']) + '</h2>'
    body += ''.join('<p><strong>' + esc(k) + '</strong><br>' + esc(v) + '</p>' for k, v in fields)
    description = event.get('description', '').strip() or '힙합/R&B 관련 공연으로, 10만 원 이하 예매가가 확인된 공연입니다.'
    body += '<p>' + esc(description[:600]) + '</p>'
    if event.get('runtime', '').strip():
        body += '<p>공연 길이: ' + esc(event['runtime']) + '</p>'
    if event.get('ticket_open_at'):
        body += '<p><strong>예매 오픈</strong><br>' + esc(event['ticket_open_at']) + '</p>'
    tickets = [t for t in event.get('tickets', []) if safe_url(t.get('url', ''))]
    if tickets:
        body += '<p><strong>예매처</strong><br>' + '<br>'.join(
            esc(t.get('name') or '공식 예매처') for t in tickets) + '</p>'
    body += '<p>일반 예매가 기준이며 수수료는 별도입니다. 잔여석과 최종 일정은 예매처에서 확인해 주세요.</p>'
    body += '<hr><p>' + esc(ATTRIBUTION) + '</p>'
    return {'subject': title[:180], 'content': body}


def poster_bytes(url):
    if not url:
        return None
    u = urlsplit(url)
    if (u.hostname not in ('kopis.or.kr', 'www.kopis.or.kr') or u.scheme not in ('http', 'https')
            or u.username or u.password or u.port not in (None, 80, 443) or not u.path.startswith('/upload/')):
        raise CafeError('Poster host/path is not an approved KOPIS image location.')
    data = transport('https://kopis.or.kr' + u.path, limit=5_000_000)
    if data.startswith(b'\xff\xd8\xff'):
        return ('poster.jpg', 'image/jpeg', data)
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return ('poster.png', 'image/png', data)
    if data.startswith((b'GIF87a', b'GIF89a')):
        return ('poster.gif', 'image/gif', data)
    raise CafeError('Poster response is not a supported image.')


def multipart(draft, poster):
    boundary = 'concert-' + uuid.uuid4().hex
    fields = {'subject': quote_plus(draft['subject']), 'content': quote_plus(draft['content']),
              'openyn': 'false', 'searchopen': 'false', 'ccl': 'false'}
    body = b''
    for name, value in fields.items():
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n'
                 f'Content-Type: text/plain; charset=UTF-8\r\n\r\n{value}\r\n').encode()
    if poster:
        filename, mime, data = poster
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\n'
                 f'Content-Type: {mime}\r\n\r\n').encode() + data + b'\r\n'
    body += f'--{boundary}--\r\n'.encode()
    return body, 'multipart/form-data; boundary=' + boundary


def publish(draft, poster, token, config):
    club, menu = str(config['club_id']), str(config['menu_id'])
    if not club.isdigit() or not menu.isdigit():
        raise CafeError('Invalid cafe or board ID.')
    body, content_type = multipart(draft, poster)
    result = json.loads(transport(f'https://openapi.naver.com/v1/cafe/{club}/menu/{menu}/articles', body,
                                  {'Authorization': 'Bearer ' + token, 'Content-Type': content_type}))
    message = result.get('message', result)
    if str(message.get('status')) != '200':
        raise CafeError('Naver did not confirm article creation. Review pending article before retrying.')
    value = message.get('result', message)
    article_id = str(value.get('articleId', ''))
    if not article_id.isdigit():
        raise CafeError('Article creation response missing ID; review pending article.')
    return {'article_id': article_id,
            'url': f'https://cafe.naver.com/f-e/cafes/{club}/articles/{article_id}',
            'announced': False}


def ensure_articles(events, state, config, now, persist, get_token=access_token,
                    load_poster=poster_bytes, create=publish):
    if state.get('cafe_pending'):
        raise CafeError('Uncertain cafe post exists. Resolve cafe_pending before retrying.')
    articles = state.setdefault('cafe_articles', {})
    token = None
    for event in sorted(events, key=lambda e: (e['start'], e['title'])):
        if not event['eligible']:
            continue
        if event['id'] not in articles:
            if token is None:
                token = get_token()
            draft = article(event)
            poster = load_poster(event.get('poster', ''))
            state['cafe_pending'] = {'event_id': event['id'], 'subject': draft['subject'],
                                     'created_at': now.isoformat(), 'target': dict(config)}
            persist()
            articles[event['id']] = create(draft, poster, token, config)
            state['cafe_pending'] = None
            persist()
        event['cafe_url'] = articles[event['id']]['url']
        event['cafe_unannounced'] = not articles[event['id']].get('announced', False)
    return events
