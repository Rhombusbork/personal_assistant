"""Google Calendar 연동: OAuth 인증과 서비스 객체 생성."""
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS = ROOT / "credentials.json"  # Google Cloud 콘솔에서 받은 OAuth 클라이언트 파일
TOKEN = ROOT / "token.json"  # 최초 인증 후 자동 생성


def get_service():
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS.exists():
                raise SystemExit(f"{CREDENTIALS} 가 없습니다. docs/google-calendar-setup.md 를 참고하세요.")
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
            creds = flow.run_local_server(port=8080, open_browser=False)
        TOKEN.write_text(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def get_or_create_calendar(service, summary, tz="Asia/Seoul"):
    for cal in service.calendarList().list().execute().get("items", []):
        if cal.get("summary") == summary:
            return cal["id"]
    cal = service.calendars().insert(body={"summary": summary, "timeZone": tz}).execute()
    return cal["id"]
