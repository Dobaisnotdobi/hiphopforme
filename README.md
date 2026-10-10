# 서울·인천 힙합/R&B 주간 공연 알림

주간 공연 알림의 초기 버전입니다. **실제 발송은 기본 비활성화이며, Secrets 등록과 명시적 활성화가 필요합니다.**
Python 3.11 이상과 GitHub Actions를 사용하며 외부 Python 패키지는 필요 없습니다.

## 구현 범위와 제한

| 항목 | 동작 |
|---|---|
| 일정 | 매주 월요일 09:17 한국 시간. GitHub 상황에 따라 지연될 수 있음 |
| 검색 범위 | 실행일 이후 120일, 서울·인천, KOPIS에 등록된 대중음악 |
| 장르 판별 | 힙합/R&B 키워드 또는 설정의 출연자 이름. 목록은 수정 가능 |
| 가격 | 일반 예매가 중 하나라도 100,000원 이하. 수수료 별도, 잔여석 미확인 |
| 신규 공연 | 처음 조건을 충족한 공연. 첫 실행은 현재 후보 전체를 신규로 발송 |
| 가격 변경 | 확인된 가격 집합 변경. 현재 10만원 초과인 공연은 알림 제외 |
| 티켓 오픈 | 공식 공지를 확인해 입력한 오픈 시각의 신규 공지 및 시각 도래 감지 |
| 종료·취소 | 제외. 정확한 종료 시각이 없는 경우 마지막 공연일 당일도 제외 |
| 변화 없음 | Discord 메시지 없음 |

**인터넷 전체를 자동 조사하는 완성형 수집기는 아닙니다.** KOPIS에 없는 소규모 공연,
SNS 단독 공지, 키워드/출연자 목록에 없는 R&B 공연은 놓칠 수 있습니다.
티켓 판매처의 공지 자동 수집은 아직 구현하지 않았습니다. KOPIS는 티켓 오픈 시각을
제공하지 않아 `data/verified.json`에 근거와 유효기간을 확인하여 보완해야 합니다.
오픈 알림은 공지된 시각 기준이며 실제 결제 가능 상태를 검증하지 않습니다.
주간 실행이므로 주중 오픈은 다음 실행 때 알립니다. 즉시 예매 알림이 필요하면 빈도를 늘려야 합니다.

가격 미정, 조건부 할인, 모호한 가격 범위는 추측하지 않고 제외합니다.
할인가와 일반가가 섞인 원문도 보수적으로 제외하므로 누락은 검토 보고서에서 확인합니다.
등록 데이터의 갱신 지연, 취소 정보 누락, 좌석 매진 여부는 보장할 수 없습니다.
기존 ChatGPT 공연 목록은 검증된 사실로 가져오지 않았습니다.

## 구조

`KOPIS 목록·상세 → 공식 공지 보완 → 지역/날짜/장르/가격 검사 → 이전 기록과 비교 → 전송 의도 저장 → Discord 수신 확인 → 발송 완료 저장`

공연 ID와 정규화한 제목·시작일·공연장으로 같은 실행의 중복을 제거합니다.
반복 실행은 저장된 공연 ID로 억제합니다. 다른 ID·다른 이름으로 등록된 동일 공연은
`config.json`의 `aliases`에 `"다른ID": "기준ID"`로 연결하세요. 자동 유사도 추정으로
서로 다른 공연을 합치지는 않습니다. 발송 기록을 지우면 기존 공연이 다시 신규로 발송됩니다.

## 사용자가 승인할 연결 — 비밀값은 채팅에 붙이지 마세요

1. **GitHub 저장소:** [새 저장소 만들기](https://github.com/new)에서 비공개
   `concert-watch` 저장소를 만듭니다. 기존 전용 저장소를 사용해도 됩니다.
   이 폴더의 내용 전체를 저장소 루트에 올립니다. `.github/workflows/weekly.yml`을
   빠뜨리지 마세요. 압축파일 하나만 업로드해서는 실행되지 않습니다.
2. Codex에서 업로드를 계속 맡기려면 GitHub 연결의 저장소 접근 선택에서 해당 저장소만
   허용합니다. [GitHub 앱 설정](https://github.com/settings/installations) 또는 Codex의
   GitHub 연결 설정에서 확인합니다. 계정 로그인과 저장소 앱 접근 허용은 별개일 수 있습니다.
   저장소 URL만 채팅으로 알려 주면 됩니다.
3. **KOPIS API 키:** [공식 Open API 신청](https://www.kopis.or.kr/por/cs/openapi/openApiInfo.do?menuId=MNU_00077)에서
   키를 발급받습니다. 이용 조건과 제공량을 직접 확인합니다.
4. **Discord:** 대상 서버의 일반 텍스트 채널 → 채널 편집 → 연동/Integrations → 웹훅에서
   웹훅을 만듭니다. 사용자는 해당 채널의 웹훅 관리 권한이 필요합니다.
   이 버전은 포럼·미디어 채널을 지원하지 않습니다. 별도 봇 토큰은 필요 없습니다.
5. **비밀 저장:** GitHub 저장소 Settings → Secrets and variables → Actions → Secrets에
   다음 두 이름으로 직접 저장합니다.
   - `DISCORD_WEBHOOK_URL`: 생성한 Discord 웹훅 URL
   - `KOPIS_API_KEY`: KOPIS 발급 키
6. **첫 검토:** Actions를 활성화하고 `Weekly concert watch` → Run workflow에서 `send`를
   체크하지 않고 실행합니다. `concert-report` 첨부의 `preview.txt`와 `report.json`을 확인합니다.
   첫 실제 API 실행에서 HTTPS 연결, 인증, 현재 필드 형식 및 수집량을 검증해야 합니다.
7. **발송 승인:** 미리보기가 맞으면 같은 설정의 Variables 탭에 `ENABLE_DISCORD`를
   값 `true`로 추가합니다. 이것이 주간 발송 활성화입니다. 첫 발송을 즉시 확인하려면
   Run workflow에서 `send`를 체크합니다. 체크하지 않은 수동 실행은 항상 미리보기입니다.
8. GitHub Actions에 저장소 `contents: write` 권한이 허용되어야 합니다. 중복 방지 상태를
   저장하기 위한 권한입니다. 전용 저장소에서 사용하는 것을 권합니다. 기본 브랜치의
   보호 규칙이 봇 기록 저장을 막으면 발송 전에 실패합니다. 보호 정책을 무턱대고 풀지 말고
   전용 저장소 사용 또는 허용되는 상태 저장소로 설계를 변경하세요.

운영 저장소는 `kyungtaeyoun/hiphopforme`입니다. Secrets 입력과 발송 활성화는 사용자가
직접 수행합니다. 저장소에 코드가 있어도 키 등록과 활성화 전에는 주간 발송하지 않습니다.

## 설정

`config.json`의 `artists`에는 이전 대화에 나온 취향 중심의 초기 목록을 넣었습니다.
지역·최대 금액·기간·아티스트 목록·제외 ID를 편집할 수 있습니다.
지역 코드 수집은 서울(11)·인천(28)으로 고정되어 있으므로 다른 도시를 추가하려면
수집 코드도 함께 변경해야 합니다. 힙합 아티스트가 포함된 혼합 장르 공연도 포함될 수 있습니다.

공식 티켓 공지 보완 예시(가상 값, 실제 발송 데이터 아님):

```json
[
  {
    "id": "kopis:PF실제공연번호",
    "verified": true,
    "verified_at": "2026-10-11",
    "valid_until": "2026-10-25",
    "evidence_url": "https://공식예매처의실제공지주소",
    "ticket_open_at": "2026-10-15T18:00:00+09:00"
  }
]
```

이 예시를 그대로 사용하지 마세요. 실제 ID·URL·시각·확인일·유효기간을 입력해야 합니다.
같은 `kopis:` ID를 쓰면 수집 결과에 합쳐집니다. 일반석 가격을 명시적으로 확인했다면
`"prices": [77000, 99000]`로 보완할 수 있습니다. KOPIS에 없는 공연을 추가할 때는
`tests/sample.json`의 필수 공연 필드를 모두 넣고 위 확인 필드도 추가하세요.
장르를 직접 확인했다면 `"genre_verified": true`를 넣을 수 있습니다.
유효기간이 지난 보완 공지는 적용하지 않으며, API 키가 없을 때 수동 자료만으로
완전한 조사가 된 것처럼 실행하지 않습니다.

## 오프라인 확인

저장소 폴더에서 실행합니다. 비밀값이나 네트워크가 필요하지 않습니다.

```text
python -m unittest discover -s tests -v
python watch.py --fixture tests/sample.json --now 2026-10-11T09:17:00+09:00
```

가상 데이터는 실제 발송과 함께 사용할 수 없습니다. 기본 실행 `python watch.py`도
미리보기만 만들며 상태를 변경하지 않습니다. 실제 실행에는 환경 변수의 두 비밀값이
필요합니다. 로컬에서는 환경 변수/비밀 관리자를 쓰고 `.env`나 키를 Git에 저장하지 마세요.

## 전송 신뢰성과 복구

Discord와 GitHub 사이에는 원자적 트랜잭션이 없으므로 완전한 exactly-once는 보장할 수 없습니다.
이 구현은 메시지를 보내기 전에 `pending` 기록을 원격 저장소에 커밋합니다.
전송 후 확인을 받고 완료 기록을 커밋합니다. 전송 시간 초과, 수신 응답 손실,
커밋 실패처럼 결과가 불확실하면 다음 실행도 멈춰 중복 자동 발송을 피합니다.
따라서 중복 억제를 위해 수동 확인이 필요한 경우가 있습니다. 상태 쓰기를 막는 권한 문제가
있으면 메시지를 보내지 않습니다. 429는 제한된 횟수 재시도하고, 불확실한 POST 실패는
자동 재시도하지 않습니다. 조회 실패는 변경 없음으로 처리하지 않고 작업 실패로 표시합니다.

`pending` 때문에 실패하면 먼저 `ENABLE_DISCORD`를 `false`로 바꾸고 실행 중인 작업이
끝났는지 확인합니다. `data/state.json`의 `pending.id`를 Discord의 `알림 ID`와 대조합니다.

- 메시지가 있으면 `pending.snapshot`을 `events[pending.event_id]`에 복사하고
  `pending`을 `null`로 바꿔 저장합니다. 기존의 다른 events 기록은 유지합니다.
- 메시지가 없다는 것을 확인했으면 `pending`만 `null`로 바꿉니다. 다음 실행이 다시 보냅니다.
- 확인이 어려우면 기록을 지우지 말고 발송 중단 상태를 유지합니다.

수정 후 미리보기로 확인하고 다시 활성화합니다. KOPIS 오류, 키 만료, 전송 실패는 GitHub
Actions 실패 알림에서 확인하세요. GitHub의 Actions 알림 구독은 사용자 계정에서 설정해야 합니다.
변화가 없을 때는 Discord에 상태 메시지를 보내지 않습니다.

## 보안 및 운영

- 비밀은 Actions Secrets에서 실행 시에만 환경 변수로 전달합니다. 코드·상태·보고서에 넣지 않습니다.
- 웹훅은 `discord.com`의 HTTPS 주소만 허용하고 리디렉션을 거부합니다.
- KOPIS도 HTTPS만 사용합니다. 실패 시 평문 HTTP로 키를 전송하는 대체 경로는 없습니다.
- 외부 API 예외 본문·URL은 로그에 출력하지 않습니다. `@everyone` 등 멘션은 비활성화합니다.
- 웹훅 URL은 전송 권한 자체입니다. 유출되면 Discord에서 폐기하고 새 값을 Secrets에 저장합니다.
- 워크플로는 공식 GitHub Actions의 메이저 버전 태그를 사용합니다. 추가 강화가 필요하면
  검토한 커밋 SHA로 고정하세요. 비공개 저장소 Actions 사용량·요금은 계정 정책을 확인하세요.
- 일시 중단: `ENABLE_DISCORD=false`. 완전 중단: 해당 workflow 비활성화.

## 근거 문서

- [KOPIS Open API 안내·이용 조건](https://www.kopis.or.kr/por/cs/openapi/openApiInfo.do?menuId=MNU_00077)
- [KOPIS API 개발가이드](https://www.kopis.or.kr/upload/openApi/공연예술통합전산망OpenAPI개발가이드.pdf)
- [GitHub Actions Secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
- [GitHub schedule 동작과 지연](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [Discord 웹훅 실행과 수신 확인](https://docs.discord.com/developers/resources/webhook#execute-webhook)

출처: (재)예술경영지원센터 공연예술통합전산망(www.kopis.or.kr).
