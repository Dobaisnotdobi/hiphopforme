# 네이버 카페 연결 준비

대상: https://cafe.naver.com/f-e/cafes/31702916/menus/36

카페 ID는 `31702916`, 게시판 ID는 `36`으로 `naver.json`에 저장했습니다.
게시판 이름·종류·계정의 글쓰기 권한은 아직 확인되지 않았습니다.
공식 API는 상품게시판에 쓸 수 없습니다. 로그인할 계정이 해당 게시판에서 직접 글을 쓸 수 있어야 합니다.

## 현재 준비된 기능

- KOPIS의 포스터·공연시간·공식 예매처를 읽어 개별 HTML 게시글 생성.
- 포스터는 KOPIS 이미지 주소만 허용하고 이미지 파일로 첨부. 없는 경우 텍스트 글 작성.
- 예매처는 이름만 표시하며 예매 링크는 본문에 넣지 않음. 포스터 파일 첨부와 링크 없는 본문으로 실제 게시 성공을 확인함.
- 네이버 계정의 refresh token으로 실행 시 access token 발급. 비밀번호는 사용하지 않음.
- 카페에 먼저 게시하고 성공한 글 번호를 저장한 뒤 Discord 요약에 카페 링크 포함.
- 신규 글은 같은 공연당 한 번. 기존 Discord 알림을 받은 공연도 최초 연결 시 카페에 한 번 게시.
- 사용자 요청에 따라 새 게시글은 전체 공개·검색 허용으로 게시. 네이버 API는 전체 공개 시 검색도 허용함. 기존 글은 변경하지 않음.
- 네이버 연결은 `ENABLE_NAVER=true`일 때만 활성화. 기본은 꺼져 있으며 기존 Discord 자동화는 유지.

카페 기존 글 자동 수정은 포함하지 않습니다. 가격·티켓 오픈 변경은 Discord의 최신 요약에 표시되며
카페 글은 최초 등록 내용이므로 필요 시 직접 수정해야 합니다. 카페 글이 삭제되어도 자동 재생성하지 않습니다.
실제 계정 승인과 디핵 공연 게시(글 번호 5469)를 완료했고 사용자가 표시 상태를 확인했습니다.

## 1. 네이버 개발자 앱 등록

https://developers.naver.com/apps/#/register 에서 로그인하고 애플리케이션을 등록합니다.

- 이름: `hiphopforme 공연 알림`
- 사용 API: 네이버 로그인 및 카페 글쓰기 권한을 선택/설정
- 서비스 환경: PC 웹
- 서비스 URL 및 Callback URL은 로그인 연결 도우미와 일치해야 합니다.
  로컬 로그인 연결을 사용할 예정이면 서비스 URL `http://127.0.0.1:8765`,
  Callback URL `http://127.0.0.1:8765/callback`을 등록합니다.
  개발자 콘솔이 해당 주소를 허용하지 않으면 임의 주소를 넣지 말고 허용되는 HTTPS 콜백으로 연결 방식을 변경합니다.
- 개발 상태에서는 게시할 계정을 테스트 사용자/멤버로 등록해야 할 수 있습니다.
  콘솔에서 요구하는 서비스 검수·권한 신청이 있으면 직접 승인 절차를 완료합니다.

## 2. 비밀정보 저장과 사용자 로그인 승인

GitHub Settings → Secrets and variables → Actions의 Secrets에 다음 이름으로 저장합니다.

- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`
- `NAVER_REFRESH_TOKEN`: 네이버 로그인 동의 후 발급받는 갱신 토큰. Client Secret과 다른 값입니다.

현재 로그인 연결 도우미는 아직 제공하지 않았습니다. 앱 등록 다음 단계에서 콜백 방식에 맞춰
사용자가 직접 네이버 로그인·동의를 수행하도록 연결해야 합니다. 비밀번호, 인증코드, 토큰은
채팅이나 저장소에 넣지 않습니다. GitHub Secrets 값은 작업자가 다시 읽을 수 없습니다.

세 값 등록 후에도 바로 활성화하지 말고, 미리보기와 게시 대상·계정·공개 범위를 확인합니다.
사용자 승인 후 `ENABLE_NAVER=true`를 등록하고 수동 실행 1회로 실제 결과를 검증합니다.

## 중단·복구

`cafe_pending`이 남으면 글 생성 결과가 불확실하므로 자동 재게시하지 않습니다.
먼저 자동화를 멈추고 해당 게시판에서 `cafe_pending.subject`와 작성 시각으로 글을 찾습니다.
글이 있으면 `cafe_articles[event_id]`에 `article_id`, 올바른 `url`, `announced:false`를 저장하고
`cafe_pending:null`로 바꿉니다. 글이 없다는 확인 후에만 pending을 지워 재시도합니다.
Discord pending을 수동 복구할 때는 게시된 공연의 `cafe_articles[id].announced`도 true로 바꿔야 합니다.
네이버 게시 후 Discord 실패가 발생해도 저장된 카페 글은 중복 생성하지 않습니다.

## 공식 문서

- https://developers.naver.com/docs/login/cafe-api/cafe-api.md
- https://developers.naver.com/docs/login/api/api.md
