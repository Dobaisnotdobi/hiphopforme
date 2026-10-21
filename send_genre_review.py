"""Send one explicitly requested review message, without publication state changes."""
import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import watch

payload = watch.read_json(watch.ROOT / 'genre-review.json')
request = Request(watch.webhook_url(), data=json.dumps(payload).encode('utf-8'),
                  headers={'Content-Type': 'application/json', 'User-Agent': 'ConcertReview/1.0'}, method='POST')
try:
    # Never retry a POST: a lost acknowledgement may still mean delivery succeeded.
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    if not result.get('id'):
        sys.exit('Acknowledgement missing. Inspect Discord before any retry.')
    print('Review delivered. Message ID: ' + result['id'])
except HTTPError as exc:
    sys.exit('Discord HTTP ' + str(exc.code) + '. No automatic retry.')
except (URLError, TimeoutError):
    sys.exit('Delivery uncertain. Inspect Discord before any retry.')
