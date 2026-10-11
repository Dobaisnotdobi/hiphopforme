"""Manual stage-one test: one plain-text article, no automatic retries."""
import json
from urllib.parse import urlencode
import naver_cafe as n


def main():
    config = json.load(open('naver.json', encoding='utf-8'))
    club, menu = str(config['club_id']), str(config['menu_id'])
    if (club, menu) != ('31702916', '36'):
        raise n.CafeError('Unexpected test destination; stopped.')
    token = n.access_token()
    print('Token refresh: success', flush=True)
    body = urlencode({'subject': '연동 테스트',
                      'content': '카페 글쓰기 연결을 확인하는 테스트입니다',
                      'openyn': 'false', 'searchopen': 'false', 'ccl': 'false'}).encode()
    result = json.loads(n.transport(
        f'https://openapi.naver.com/v1/cafe/{club}/menu/{menu}/articles', body,
        {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/x-www-form-urlencoded'}))
    message = result.get('message', result)
    value = message.get('result', message)
    article_id = str(value.get('articleId', ''))
    if str(message.get('status')) == '200' and article_id.isdigit():
        print(f'Plain test success: https://cafe.naver.com/f-e/cafes/{club}/articles/{article_id}')
    else:
        raise n.CafeError('Creation not confirmed; inspect board before any retry.')


if __name__ == '__main__':
    try:
        main()
    except n.CafeError as exc:
        raise SystemExit(str(exc))
    except Exception:
        raise SystemExit('Unexpected failure; sensitive details suppressed. Do not retry automatically.')
