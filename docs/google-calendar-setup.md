# Google Calendar 연동 설정 (최초 1회)

1. https://console.cloud.google.com 접속 → 새 프로젝트 생성 (예: `personal-assistant`)
2. **API 및 서비스 → 라이브러리** → "Google Calendar API" 검색 → **사용 설정**
3. **OAuth 동의 화면** → 사용자 유형 **외부** → 앱 이름/이메일 입력
   → **테스트 사용자**에 본인 Google 계정 추가
4. **사용자 인증 정보 → 사용자 인증 정보 만들기 → OAuth 클라이언트 ID**
   → 애플리케이션 유형 **데스크톱 앱** → 생성 후 JSON 다운로드
5. 다운로드한 파일을 프로젝트 루트에 `credentials.json` 으로 저장 (git 에는 올라가지 않음)

## 실행

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pa.sync_timetable --dry-run   # 미리보기
python -m pa.sync_timetable             # 수업 시간표 동기화
bin/pa run --full                       # 전체 동기화: Canvas → 계획 → 마감 캘린더(알림 포함)
```

처음 실행 시 터미널에 출력되는 URL 을 브라우저에서 열어 로그인/허용하면
`token.json` 이 생성되고 이후로는 자동 인증된다.
Google Calendar 에 **"수업 시간표"** 캘린더가 새로 생기고 수업이 매주 반복 일정으로 들어간다.
