"""Google Calendar 연동: OAuth 인증과 서비스 객체 생성."""
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from pa.config import ROOT

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS = ROOT / "credentials.json"  # Google Cloud 콘솔에서 받은 OAuth 클라이언트 파일
TOKEN = ROOT / "token.json"  # 최초 인증 후 자동 생성


class GoogleAuthError(RuntimeError):
    pass


AUTH_HELP = ("Google Calendar 로그인이 만료됐습니다 — 대시보드의 [Google 다시 로그인] 또는 터미널에서 "
             "bin/pa google-login (브라우저가 열리면 허용). 7일마다 반복되면 Google Cloud 앱을 '프로덕션'으로 바꿔야 함 "
             "(docs/usage.md 'Google 로그인')")


def get_service():
    """엔진용: 저장된 로그인으로만. 없거나 만료되면 GoogleAuthError (엔진이 브라우저를 기다리며 멈추지 않게)."""
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if not creds:
        raise GoogleAuthError(AUTH_HELP)
    if not creds.valid:
        if not (creds.expired and creds.refresh_token):
            raise GoogleAuthError(AUTH_HELP)
        try:
            creds.refresh(Request())
        except RefreshError as e:  # 'invalid_grant' — 로그인 만료 (테스트 앱은 7일)
            raise GoogleAuthError(AUTH_HELP) from e
        TOKEN.write_text(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def login():
    """사용자가 직접 실행: 브라우저(Windows)로 Google 로그인 → token.json 저장."""
    import webbrowser
    if not CREDENTIALS.exists():
        raise SystemExit(f"{CREDENTIALS} 가 없습니다. docs/google-calendar-setup.md 를 참고하세요.")
    webbrowser.register("wsl-windows", None, webbrowser.GenericBrowser("explorer.exe"))
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
    creds = flow.run_local_server(port=8080, open_browser=True, browser="wsl-windows", timeout_seconds=600,
                                  access_type="offline", prompt="consent")
    TOKEN.write_text(creds.to_json())
    print("✅ Google 로그인 저장됨")


def get_or_create_calendar(service, summary, tz="Asia/Seoul"):
    for cal in service.calendarList().list().execute().get("items", []):
        if cal.get("summary") == summary:
            return cal["id"]
    cal = service.calendars().insert(body={"summary": summary, "timeZone": tz}).execute()
    return cal["id"]
