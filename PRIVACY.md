# 개인정보 처리방침 (Privacy Policy)

이 프로그램(개인 비서, personal_assistant)은 각 사용자가 **자기 컴퓨터에서 직접 실행하는** 개인용 일정 관리 도구입니다.
운영하는 서버가 없고, 사용자 정보를 개발자나 다른 곳으로 보내지 않습니다.

## Google 캘린더에서 하는 일

- 권한: `https://www.googleapis.com/auth/calendar`
- 사용자의 캘린더 목록에서 이 프로그램용 마감 캘린더를 찾고, 없으면 하나 만듭니다.
- 그 캘린더에 과제·시험 마감 일정을 넣고, 바꾸고, 지웁니다.
  이 프로그램이 만든 일정(표시가 붙은 것)만 고치며, 다른 일정은 읽거나 바꾸지 않습니다.

## 저장과 공유

- Google 로그인 정보(`token.json`)와 일정 데이터는 **사용자 컴퓨터에만** 저장됩니다.
- 어떤 데이터도 제3자에게 팔거나 공유하지 않으며, 광고에 쓰지 않습니다.
- Google API 에서 받은 정보는 [Google API 서비스 사용자 데이터 정책](https://developers.google.com/terms/api-services-user-data-policy)
  (제한적 사용 요건 포함)을 따릅니다.

## 권한 끊기

- https://myaccount.google.com/permissions 에서 언제든 이 앱의 접근을 없앨 수 있습니다.
- 컴퓨터에서 `token.json` 을 지우면 저장된 로그인도 사라집니다.

---

**English summary:** This is a personal scheduling tool that each user runs on their own computer. There is no server.
It uses the Google Calendar scope only to create one deadline calendar and add, update, or delete the events it created there.
Tokens and data stay on the user's computer. Nothing is sold or shared with third parties.
Use of information received from Google APIs follows the Google API Services User Data Policy, including the Limited Use
requirements. You can revoke access at any time at https://myaccount.google.com/permissions.
