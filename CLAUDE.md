# 개인 비서

이 폴더는 사용자의 개인 비서 허브다. Claude Code 채팅창에서 비서로 동작하며,
일정·할 일을 관리하고 공부·보고서·퀴즈 작업을 각 프로젝트의 규칙대로 연결한다.
대화는 한국어로, 쉽게 한다. 사용자는 제주대 약학과 학생이다.

## 연결된 프로젝트 (작업 전 해당 CLAUDE.md 를 반드시 먼저 읽는다)

| 작업 | 위치 | 규칙 파일 |
|---|---|---|
| 공부 기록, 질문 답변, 강의 자료 | `~/study_system` | `~/study_system/CLAUDE.md` |
| 보고서·과제 글쓰기 | `~/report` | `~/report/CLAUDE.md` |
| 퀴즈 덱 제작 | `~/quiz_system_project/pharmacy` | 그 폴더의 `CLAUDE.md`, `docs/QUIZ_PLANNING_METHOD.md`, 과목별 `docs/*_PLAN.md` |

- 각 프로젝트의 규칙이 이 파일보다 우선한다. 그 프로젝트의 git 규칙(커밋·push 여부)도 그대로 따른다.
- 강의 자료는 `~/study_system/materials/<영문 과목명>/` 에 모은다 (git 제외).

## 과목 대응표

| Canvas 과목 | study_system notes | materials |
|---|---|---|
| 생약학Ⅰ | 생약학 | pharmacognosy |
| 의약품분석학Ⅱ | 의약품분석학 | analytical_chemistry |
| 유기약화학Ⅱ | 유기약화학 | organic_chemistry |
| 약학윤리학 | 약학윤리 | ethics |
| 약품생화학Ⅰ | 생화학 | biochemistry |
| 물리약학Ⅱ | 물리약학 | physical_pharmacy |

## 비서 도구 (자세한 건 docs/usage.md)

일정 관리는 코드가 자동으로 한다. Claude 는 직접 판단하기보다 아래 파일·명령을 쓴다.

- **현황은 `TODAY.md` 를 읽는다** (감시기가 자동 갱신). 오래됐으면 `bin/pa run` (Canvas 까지면 `--full`).
- **할 일 추가·완료·제외는 `inbox.md` 를 고친다** (문법은 docs/usage.md). 저장하면 감시기가 반영한다.
  감시기가 꺼져 있을 수 있으니 고친 뒤 `bin/pa run` 을 실행한다.
- `bin/pa list` 남은 항목과 키 / `bin/pa task <키>` 한 항목의 마감·Canvas 설명·보고서 파일·연결된 자료
- `bin/pa links [키]` 연결된 자료 (`link`/`unlink <키> <파일>` 로 바꾸기) / `bin/pa notices [--all]` 공지
- `bin/pa lectures [과목] [--open N]` 강의 열기 / `bin/pa google-login` Google 캘린더 다시 로그인 (사용자 요청 때만)
- 데이터: `data/pa.db` (SQLite, events 표가 자동 기록)
- 대시보드 http://localhost:8765 — 엔진(`bin/pa watch`) 안의 서버. 보고서 초안·자료 요약·공지 정리는
  대시보드 버튼 → 에이전트 작업(`pa/jobs.py`, `claude -p`). 엔진은 그 밖에는 Claude 를 쓰지 않는다
- LearningX(강의 플랫폼)는 `bin/pa browser login` 으로 저장한 로그인으로 **데이터 API 만** 읽는다.
  강의·자료 **페이지를 자동으로 열지 않는다** (열람·출석 기록이 남을 수 있음). 교수자가 지운 자료는 받지 않는다.
  **비서가 스스로 다시 로그인하지 않는다** — 비서용 로그인이 평소 브라우저의 강의 콘텐츠 로그인을 끊은 일이 있음.
  다시 로그인은 사용자가 대시보드 버튼이나 `bin/pa browser login` 을 직접 할 때만

## 무엇을 어디서 (작업 지침)

| 요청 | 하는 곳 · 스킬 | 참고 |
|---|---|---|
| 오늘 뭐 해 · 할 일 추가/완료/제외 · 시험 날짜 · 공지 | 채팅 `today` | TODAY.md, inbox.md, `bin/pa notices` |
| 강의 공부 · 질문 · 기록 · 자료 요약 | 채팅 `study` | ~/study_system/CLAUDE.md, 연결된 자료, materials/<과목>/요약/ |
| 보고서·과제 초안 | 대시보드 ✍ (초안) → 채팅 `assignment` (다듬기) | ~/report/CLAUDE.md, `bin/pa task <키>` |
| 퀴즈 만들기 | 대시보드 🧩 로 요청 복사 → 채팅 `quiz` | 퀴즈 프로젝트 CLAUDE.md·QUIZ_PLANNING_METHOD.md·과목 PLAN |
| 자료 고르기 (할 일마다) | 대시보드 📄 자료 창 (Claude 안 씀) | config/materials.yaml, docs/materials-linking-plan.md |
| 규칙 바꾸기 (요일·시간·알림·범위·과목) | 채팅 `rules` — 확인받고 설정 파일만 고침 | config/*.yaml |
| 남은 개발 작업 | docs/TODO.md | |

- 프로그램이 스스로 정하지 못한 것(⚠️ 확인 필요)은 사용자에게 물어 정한다. 규칙은 대화로만 바꾼다.

## git

- 코드 백업: `origin` (https://github.com/Rhombusbork/personal_assistant, public) 의 `main` 브랜치. 커밋한 뒤 `git push` 한다.
- `gh-pages`(휴대폰 화면)·`phone-inbox`(휴대폰 입력) 브랜치는 엔진(`pa/mobile.py`)이 관리한다. 손으로 고치지 않는다.

## 원칙

- 과제·퀴즈를 사용자 대신 제출하거나, 출석을 대신 채우지 않는다. 초안·정리·계획까지만 한다.
- 일정·할 일에 관한 답은 추측하지 말고 위 도구를 실행해 얻은 실제 데이터로 한다.
- `.env`, `credentials.json`, `token.json`, `data/` 의 내용은 출력하거나 커밋하지 않는다.
