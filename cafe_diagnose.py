"""Check authentication and Cafe API rejection without supplying article content."""
import json
import re
from urllib.error import HTTPError
from urllib.request import Request, build_opener
import naver_cafe as n


def safe_code(value):
    allowed = {'0005', '024', '028', '403', '999', 'invalid_request', 'invalid_client', 'unauthorized_client'}
    allowed.update('AP%03d' % i for i in range(1, 9))
    allowed.update('CA%03d' % i for i in range(1, 5))
    if isinstance(value, int):
        value = str(value)
    return value if isinstance(value, str) and (value in allowed or re.fullmatch(r'[A-Z]{0,3}[0-9]{1,5}', value)) else 'unrecognized'


def main():
    token = n.access_token()
    print('Token refresh: success')
    config = json.load(open('naver.json', encoding='utf-8'))
    club, menu = str(config['club_id']), str(config['menu_id'])
    if not club.isdigit() or not menu.isdigit():
        raise n.CafeError('Invalid target')
    # Required subject and content are deliberately absent. This cannot form an article.
    req = Request(f'https://openapi.naver.com/v1/cafe/{club}/menu/{menu}/articles',
                  data=b'', headers={'Authorization': 'Bearer ' + token,
                                     'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        response = build_opener(n.NoRedirect).open(req, timeout=30)
    except HTTPError as exc:
        response = exc
    with response:
        print('Cafe validation HTTP:', response.code)
        data = json.loads(response.read(20000))
    message = data.get('message', {})
    error = message.get('error', {}) if isinstance(message, dict) else {}
    code = data.get('errorCode', data.get('error_code', data.get('code')))
    if code is None and isinstance(error, dict):
        code = error.get('code', error.get('errorCode'))
    print('Cafe validation code:', safe_code(code))
    # No error messages, raw responses, tokens or identifiers are logged.


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Diagnostic failed; sensitive response suppressed.')
