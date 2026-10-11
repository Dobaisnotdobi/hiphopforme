"""KOPIS-based weekly concert monitor. Python 3.11+, standard library only."""
import argparse
import copy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unicodedata
import uuid
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import xml.etree.ElementTree as ET

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent


def encode_payload(payload):
    if payload is None:
        return None, "application/json"
    payload = dict(payload)
    attachment = payload.pop("_attachment_text", None)
    if attachment is None:
        return json.dumps(payload).encode(), "application/json"
    boundary = "concert-" + uuid.uuid4().hex
    payload["attachments"] = [{"id": 0, "filename": "concerts.txt"}]
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\n'
            'Content-Type: application/json\r\n\r\n').encode()
    body += json.dumps(payload).encode() + b'\r\n'
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="files[0]"; filename="concerts.txt"\r\n'
             'Content-Type: text/plain; charset=utf-8\r\n\r\n').encode()
    body += attachment.encode('utf-8') + f'\r\n--{boundary}--\r\n'.encode()
    return body, "multipart/form-data; boundary=" + boundary


class SafeError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SafeError("Redirect refused; check API endpoint (URL suppressed).")


def request(url, payload=None):
    """Never log URLs: the KOPIS query and Discord path contain credentials."""
    data, content_type = encode_payload(payload)
    for attempt in range(4):
        req = Request(url, data=data,
                      headers={"User-Agent": "ConcertWatch/1.0", "Content-Type": content_type})
        try:
            with build_opener(NoRedirect).open(req, timeout=30) as response:
                return response.read(5_000_000)
        except HTTPError as exc:
            # Discord 429 is an explicit rejection; other POST failures are ambiguous.
            # KOPIS has returned intermittent 400 responses for valid detail IDs.
            # Retry GET only; never retry an ambiguous Discord POST.
            if attempt < 3 and (exc.code == 429 or (payload is None and (exc.code == 400 or exc.code >= 500))):
                try:
                    wait = float(exc.headers.get("Retry-After", 2 ** attempt))
                except ValueError:
                    wait = 2 ** attempt
                time.sleep(min(max(wait, 1), 60))
                continue
            raise SafeError(f"HTTP {exc.code}; credentials and response suppressed.") from None
        except SafeError:
            raise
        except Exception:
            raise SafeError("Network request failed; credentials suppressed.") from None


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save_json(path, value):
    path = Path(path)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def normal(text):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", text).casefold())


def has_term(text, term):
    # Short Latin artist names must not match fragments of unrelated words.
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(term.casefold()) + r"(?![a-z0-9])", text.casefold()))


def prices(text):
    # Conditional discounts and ambiguous ranges are not treated as normal seats.
    if re.search(r"할인|회원|장애|국가유공|학생|카드|패키지|부터|~|～", text):
        return []
    values = [int(x.replace(",", "")) for x in re.findall(r"(?<![\d.,])(\d[\d,]*)\s*원", text)]
    if not values and text.strip() in ("무료", "전석 무료"):
        return [0]
    return sorted(set(values))


def parse_date(value):
    return date.fromisoformat(value.replace(".", "-"))


def parse_time(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise SafeError("ticket_open_at must contain timezone, e.g. +09:00.")
    return result


def api(path, key, **params):
    try:
        body = request("https://kopis.or.kr/openApi/restful/" + path + "?" +
                       urlencode({"service": key, **params}))
    except SafeError as exc:
        raise SafeError(f"{exc} Lookup: {path}; filters: {json.dumps(params)}") from None
    try:
        tree = ET.fromstring(body)
    except ET.ParseError:
        raise SafeError("KOPIS returned invalid XML.") from None
    if tree.tag != "dbs":
        raise SafeError("KOPIS authentication or API error; response suppressed.")
    return tree.findall("db")


def collect(config, now):
    key = os.environ.get("KOPIS_API_KEY")
    if not key:
        raise SafeError("Add KOPIS_API_KEY to GitHub Actions Secrets.")
    ids = set()
    start = now.date()
    limit = start + timedelta(days=config["lookahead_days"])
    # API accepts at most 31 days per request. No genre-code guess is needed:
    # fetch both regions, then filter the official genre name before detail calls.
    while start <= limit:
        end = min(start + timedelta(days=30), limit)
        for region in ("11", "28"):
            for page in range(1, 1000):
                rows = api("pblprfr", key, stdate=start.strftime("%Y%m%d"),
                           eddate=end.strftime("%Y%m%d"), cpage=page, rows=100,
                           signgucode=region)
                for row in rows:
                    if row.findtext("genrenm") == "대중음악":
                        ids.add(row.findtext("mt20id"))
                if len(rows) < 100:
                    break
            else:
                raise SafeError("Pagination limit reached; refusing partial collection.")
        start = end + timedelta(days=1)
    result = []
    for event_id in sorted(ids):
        if not event_id or not re.fullmatch(r"PF\d+", event_id):
            raise SafeError("Invalid KOPIS event ID.")
        rows = api("pblprfr/" + event_id, key)
        if len(rows) != 1:
            raise SafeError("KOPIS detail missing; refusing partial collection.")
        row = rows[0]
        get = lambda name: row.findtext(name, default="")
        result.append({"id": "kopis:" + event_id, "title": get("prfnm"),
                       "venue": get("fcltynm"), "region": get("area"),
                       "start": get("prfpdfrom").replace(".", "-"),
                       "end": get("prfpdto").replace(".", "-"),
                       "artists": get("prfcast"), "price_text": get("pcseguidance"),
                       "runtime": get("prfruntime"),
                       "prices": prices(get("pcseguidance")), "status": get("prfstate"),
                       "url": "https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?mt20Id=" + event_id,
                       "source": "KOPIS", "ticket_open_at": None})
        time.sleep(0.15)
    return result


def merge_verified(events, verified, now):
    """Explicitly reviewed official notices; not generated/inferred ticket dates."""
    by_id = {e["id"]: e for e in events}
    for item in verified:
        if not item.get("verified") or parse_date(item["valid_until"]) < now.date():
            continue
        if not item.get("evidence_url", "").startswith("https://"):
            raise SafeError("Verified notice requires an HTTPS evidence URL.")
        if parse_date(item["verified_at"]) > now.date():
            raise SafeError("Verified notice cannot be dated in the future.")
        event_id = item["id"]
        base = by_id.get(event_id, {})
        event = {**base, **{k: v for k, v in item.items() if k not in
                           ("verified", "valid_until", "verified_at")}}
        # Preserve evidence internally, without displaying source URLs in Discord.
        event["url"] = item["evidence_url"]
        event["source"] = "공식 공지 확인 + " + base.get("source", "수동 보완")
        by_id[event_id] = event
    return list(by_id.values())


def prepare(events, config, now):
    output, seen, rejected = [], set(), []
    for original in events:
        e = copy.deepcopy(original)
        reason = None
        if e["id"] in config["exclude_ids"]:
            reason = "excluded"
        elif not any(e["region"].startswith(r) for r in config["regions"]):
            reason = "region"
        # Exclude the entire final date when the source lacks exact end time.
        # This deliberately avoids posting an already-finished same-day show.
        elif parse_date(e["end"]) <= now.date():
            reason = "ended_or_final_day"
        elif parse_date(e["start"]) > now.date() + timedelta(days=config["lookahead_days"]):
            reason = "outside_window"
        elif any(t in e.get("status", "") for t in ("취소", "종료", "cancelled", "canceled")):
            reason = "cancelled_or_ended"
        elif not (e.get("genre_verified") is True or any(has_term(e["title"] + " " + e.get("artists", ""), t)
                      for t in config["keywords"] + config["artists"])):
            reason = "genre_unconfirmed"
        p = e.get("prices", [])
        if not isinstance(p, list) or any(type(v) is not int or v < 0 for v in p):
            raise SafeError("Price must be a list of nonnegative integer KRW amounts.")
        if reason:
            rejected.append({"id": e["id"], "reason": reason})
            continue
        e["prices"] = sorted(set(p))
        e["eligible"] = bool(p) and min(p) <= config["max_price_krw"]
        if not e["eligible"]:
            rejected.append({"id": e["id"], "reason": "price_unknown_or_over_budget"})
        key = config["aliases"].get(e["id"], e["id"])
        identity = normal(e["title"]) + "|" + e["start"] + "|" + normal(e["venue"])
        if key in seen or identity in seen:
            continue
        seen.update((key, identity))
        e["id"] = key
        if e.get("ticket_open_at"):
            parse_time(e["ticket_open_at"])
        if urlsplit(e["url"]).scheme not in ("https", "http"):
            raise SafeError("Invalid evidence URL.")
        output.append(e)
    return output, rejected


def changes(event, previous, now, budget):
    if not event["eligible"]:
        return []
    reasons = []
    if not previous or not previous.get("notified"):
        reasons.append("신규 공연")
    elif previous["prices"] and previous["prices"] != event["prices"]:
        old = ", ".join(f"{p:,}원" for p in previous["prices"])
        reasons.append("가격 변경 (이전: " + old + ")")
    opened = event.get("ticket_open_at")
    if opened:
        open_time = parse_time(opened)
        stage = "open" if open_time <= now else "announced"
        marker = opened + ":" + stage
        if marker not in (previous or {}).get("open_notices", []):
            reasons.append("티켓 오픈" if stage == "open" else "티켓 오픈 예정")
    return reasons


def next_snapshot(event, previous, now, sent):
    snap = copy.deepcopy(previous or {"notified": False, "open_notices": []})
    # Do not erase a known price with missing data; remember over-budget prices.
    if event["prices"]:
        snap["prices"] = event["prices"]
    snap["last_seen"] = now.isoformat()
    if sent:
        snap["notified"] = True
        if event.get("ticket_open_at"):
            stage = "open" if parse_time(event["ticket_open_at"]) <= now else "announced"
            marker = event["ticket_open_at"] + ":" + stage
            if marker not in snap["open_notices"]:
                snap["open_notices"].append(marker)
    return snap


def message(event, reasons, now, config=None):
    def clean(value, limit):
        value = re.sub(r'https?://\S+', '', str(value))
        return ' '.join(value.replace('@', '＠').replace('`', "'").split())[:limit]
    artists = event.get('artists', '').strip()
    if not artists:
        artists = ', '.join(a for a in (config or {}).get('artists', []) if has_term(event['title'], a)) or '출연진 미공개'
    dates = event['start'] if event['start'] == event['end'] else event['start'] + ' ~ ' + event['end']
    details = [' / '.join(reasons), f"예매가 {min(event['prices']):,}원부터"]
    if event.get('runtime', '').strip():
        details.append(event['runtime'].strip())
    if event.get("ticket_open_at"):
        details.append('예매 오픈 ' + parse_time(event['ticket_open_at']).astimezone(KST).strftime('%m/%d %H:%M'))
    lines = ["공연명: " + clean(event['title'], 200),
             "아티스트: " + clean(artists, 200), "일자: " + dates,
             "장소: " + clean(event['venue'], 160), "설명: " + clean(' · '.join(details), 400)]
    return {"content": '\n'.join(lines), "allowed_mentions": {"parse": []}}


def batch_message(planned, now, config):
    text = '\n\n'.join(message(e, reasons, now, config)['content'] for e, reasons in planned)
    payload = {"content": text, "allowed_mentions": {"parse": []}}
    # One Discord message even when the full list exceeds the text limit.
    # Count UTF-16 units conservatively, including non-BMP characters.
    if len(text.encode('utf-16-le')) // 2 > 1900:
        payload['content'] = f"공연 알림 {len(planned)}건을 한 파일로 묶었습니다."
        payload['_attachment_text'] = text
    return payload


def webhook_url():
    value = os.environ.get("DISCORD_WEBHOOK_URL", "")
    u = urlsplit(value)
    if (u.scheme != "https" or u.hostname != "discord.com" or u.port not in (None, 443)
            or u.username or u.password or u.query or u.fragment
            or not re.fullmatch(r"/api(?:/v\d+)?/webhooks/\d+/[\w-]+", u.path)):
        raise SafeError("DISCORD_WEBHOOK_URL must be a Discord HTTPS webhook for a text channel.")
    return value + "?wait=true"


def checkpoint(path, state, use_git):
    save_json(path, state)
    if not use_git:
        return
    relative = str(Path(path).resolve().relative_to(ROOT)).replace("\\", "/")
    for args in (["git", "add", "--", relative],
                 ["git", "commit", "--allow-empty", "-m", "Persist concert delivery state"],
                 ["git", "push", "origin", "HEAD"]):
        completed = subprocess.run(args, cwd=ROOT, capture_output=True)
        if completed.returncode:
            raise SafeError("State checkpoint failed; delivery stopped. Check branch write permission.")


def deliver(events, state, config, now, path, use_git=False, send=request):
    if state.get("pending"):
        raise SafeError("Uncertain delivery exists. Resolve pending state before retrying; see README.")
    url = webhook_url()  # Validate before touching the persistent state.
    planned, snapshots = [], {}
    for event in events:
        previous = state["events"].get(event["id"])
        reasons = changes(event, previous, now, config["max_price_krw"])
        snapshots[event['id']] = next_snapshot(event, previous, now, bool(reasons))
        if reasons:
            planned.append((event, reasons))
    if planned:
        planned.sort(key=lambda item: (item[0]['start'], item[0]['title']))
        payload = batch_message(planned, now, config)
        delivery_id = hashlib.sha256(json.dumps(snapshots, sort_keys=True).encode()).hexdigest()[:12]
        # Persist the entire batch intent before the single network operation.
        state['pending'] = {'id': delivery_id, 'snapshots': snapshots,
                            'event_ids': [e['id'] for e, _ in planned],
                            'created_at': now.isoformat(), 'payload': payload}
        checkpoint(path, state, use_git)
        response = json.loads(send(url, payload))
        if not response.get('id'):
            raise SafeError('Discord acknowledgement missing; pending delivery requires review.')
        state['last_delivery'] = {'id': delivery_id, 'message_id': response['id'],
                                  'event_ids': [e['id'] for e, _ in planned]}
        state['pending'] = None
    state['events'].update(snapshots)
    checkpoint(path, state, use_git)
    return len(planned)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Actually send to Discord")
    parser.add_argument("--git-checkpoint", action="store_true")
    parser.add_argument("--fixture", help="Offline sample input (never allowed with --send)")
    parser.add_argument("--now", help="Offline sample timestamp, timezone required")
    args = parser.parse_args()
    if args.send and (args.fixture or args.now):
        raise SafeError("Fixtures and artificial dates cannot be used for live sending.")
    now = parse_time(args.now).astimezone(KST) if args.now else datetime.now(KST)
    config = read_json(ROOT / "config.json")
    state_path = ROOT / "data/state.json"
    state = read_json(state_path)
    if state.get("version") != 1 or not isinstance(state.get("events"), dict):
        raise SafeError("Invalid state; do not reset it automatically.")
    if state.get("pending"):
        raise SafeError("Pending uncertain delivery; see README recovery steps.")
    raw = read_json(args.fixture) if args.fixture else collect(config, now)
    raw = merge_verified(raw, read_json(ROOT / "data/verified.json"), now)
    events, rejected = prepare(raw, config, now)
    planned = [(e, reasons) for e in events
               if (reasons := changes(e, state["events"].get(e["id"]), now, config["max_price_krw"]))]
    planned.sort(key=lambda item: (item[0]['start'], item[0]['title']))
    payload = batch_message(planned, now, config) if planned else None
    save_json(ROOT / "report.json", {"checked_at": now.isoformat(), "collected": len(raw),
              "retained": len(events), "notifications": len(planned),
              "discord_messages": int(bool(planned)), "excluded": rejected})
    (ROOT / "preview.txt").write_text((payload.get('_attachment_text', payload['content']) if payload
                                      else "변경 사항 없음"), encoding="utf-8")
    if args.send:
        count = deliver(events, state, config, now, state_path, args.git_checkpoint)
        print(f"Delivered {count} concert updates in {int(bool(count))} message(s).")
    else:
        print(f"Preview only: {len(planned)} notices. State unchanged; no Discord requests.")


if __name__ == "__main__":
    try:
        main()
    except SafeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("Validation or runtime failure; details suppressed to protect secrets. Run offline tests.", file=sys.stderr)
        sys.exit(1)
