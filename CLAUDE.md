# 개인 비서

이 폴더는 사용자의 개인 비서 허브다. Claude Code 채팅창에서 비서로 동작하며,
일정·할 일을 관리하고 공부·보고서·퀴즈 작업을 각 프로젝트의 규칙대로 연결한다.
대화는 한국어로, 쉽게 한다.

사용자 소개·과목 대응표·내 저장소는 `config/profile.md` 에 있다 (git 제외, 견본은 `config/profile.example.md`):

@config/profile.md

## 연결된 프로젝트 (작업 전 해당 CLAUDE.md 를 반드시 먼저 읽는다)

| 작업 | 위치 | 규칙 파일 |
|---|---|---|
| 공부 기록, 질문 답변, 강의 자료 | `~/study_system` | `~/study_system/CLAUDE.md` |
| 보고서·과제 글쓰기 | `~/report` | `~/report/CLAUDE.md` |
| 퀴즈 덱 제작 | `~/quiz_system_project/pharmacy` | 그 폴더의 `CLAUDE.md`, `docs/QUIZ_PLANNING_METHOD.md`, 과목별 `docs/*_PLAN.md` |
| HRA 텍스트(한글 hwpx 보고서) 작성 | `~/hra` (고전 `classic/`, 경영서 `business_book/`) | `~/hra/CLAUDE.md`. **hwpx 는 직접 다루지 말고 원고 .md → `hra-write` → `hra-fix`** (`~/hra/text/docs/WRITE.md`) |

- 각 프로젝트의 규칙이 이 파일보다 우선한다. 그 프로젝트의 git 규칙(커밋·push 여부)도 그대로 따른다.
- 강의 자료는 `~/study_system/materials/<영문 과목명>/` 에 모은다 (git 제외).

## 추가자료 폴더 (작업용 임시 보관)

- 사용자가 작업에 쓸 사진·파일을 넘길 때는 `추가자료/<과목 또는 작업명>/` 에 둔다 (git 제외).
  비서 폴더 바로 아래에 새 폴더로 넣었으면 `추가자료/` 아래로 옮긴다.
- **작업이 끝날 때마다** `추가자료/` 에 남은 파일이 있으면 목록(폴더·개수)을 보여 주고 하나씩 묻는다:
  1. `~/study_system/materials/<영문 과목명>/` 안의 어디로 옮길지 (하위 폴더를 제안, 예: `조별학습/11주/`)
  2. 지울지
  3. 그대로 둘지
  허락 없이 옮기거나 지우지 않는다. 같은 파일이 중복(`(1)` 붙은 복사본 등)이면 함께 알려 준다.

## 비서 도구 (자세한 건 docs/usage.md)

일정 관리는 코드가 자동으로 한다. Claude 는 직접 판단하기보다 아래 파일·명령을 쓴다.

- **두 노트북을 같이 쓴다** (`pa/peer.py`, 비공개 저장소 `.env` 의 `PA_STATE_REPO`). 한 번에 한 PC(일하는 PC)만 Canvas·계획·캘린더를 하고,
  다른 PC(대기)는 30초마다 그 기록으로 맞춘다. 대기 PC 에서도 inbox.md 를 고치고 `bin/pa run` 하면 일하는 PC 로 넘어간다 (1~2분).
  TODAY.md 에 "🖥 대기 PC" 가 보이면 그 PC 다. 상태는 `bin/pa peer` (docs/usage.md '두 PC 같이 쓰기')
- **현황은 `TODAY.md` 를 읽는다** (감시기가 자동 갱신). 오래됐으면 `bin/pa run` (Canvas 까지면 `--full`).
- **할 일 추가·완료·제외는 `inbox.md` 를 고친다** (문법은 docs/usage.md). 저장하면 감시기가 반영한다.
  감시기가 꺼져 있을 수 있으니 고친 뒤 `bin/pa run` 을 실행한다.
- `bin/pa list` 남은 항목과 키 / `bin/pa task <키>` 한 항목의 마감·Canvas 설명·보고서 파일·연결된 자료
- `bin/pa links [키]` 연결된 자료 (`link`/`unlink <키> <파일>` 로 바꾸기) / `bin/pa notices [--all]` 공지
- `bin/pa pull` 내 git 저장소(`config/repos.yaml`)를 GitHub 과 대조해 내려받기 — 엔진은 켤 때 한 번 자동.
  휴대폰·클라우드 세션에서 고친 기록이 PC 로 들어온다. 갈라지면 '⚠️ 확인 필요' → 채팅에서 합친다
- `bin/pa lectures [과목] [--open N]` 강의 열기 / `bin/pa google-login` Google 캘린더 다시 로그인 (사용자 요청 때만)
- 데이터: `data/pa.db` (SQLite, events 표가 자동 기록)
- 대시보드 http://localhost:8765 — 엔진(`bin/pa watch`) 안의 서버. 보고서 초안·자료 요약·공지 정리는
  대시보드 버튼 → 에이전트 작업(`pa/jobs.py` → `pa/ai.py`: `.env` 의 `PA_AI` 에 따라 `claude -p` 또는 `codex exec`). 엔진은 그 밖에는 AI 를 쓰지 않는다
- LearningX(강의 플랫폼)는 `bin/pa browser login` 으로 저장한 로그인으로 데이터 API를 읽고, 필요하다면 자동으로 로그인한다.
  로그인이 끊기면 `.env` 의 `PA_SCHOOL_ID`·`PA_SCHOOL_PW` 로 엔진이 안 보이는 브라우저에서 자동 로그인한다 (30분에 한 번까지,
  2026-11-16 사용자가 정함 — 평소 브라우저의 강의 콘텐츠 로그인이 끊길 수 있음을 알고 고름). 계정이 없거나 실패하면 대시보드 버튼·`bin/pa browser login`
- 수업 시간표는 학교 포털(하영드리미)에서 **매주 첫 전체 확인 때 읽어 온다** (2026-11-16 사용자가 정함, `pa/portal.py`, `bin/pa timetable`).
  읽기만 한다. 대면 과목은 `config/timetable.yaml` 의 `portal.offline` 에 적은 것만 (포털은 온라인 과목에도 강의실을 적음) —
  '처음 보는 과목' 경고가 뜨면 사용자에게 대면인지 묻고 offline/online 에 적는다

## 무엇을 어디서 (작업 지침)

| 요청 | 하는 곳 · 스킬 | 참고 |
|---|---|---|
| 오늘 뭐 해 · 할 일 추가/완료/제외 · 시험 날짜 · 공지 | 채팅 `today` | TODAY.md, inbox.md, `bin/pa notices` |
| 강의 공부 · 질문 · 기록 · 자료 요약 | 채팅 `study` | ~/study_system/CLAUDE.md, 연결된 자료, materials/<과목>/요약/ |
| 보고서·과제 초안 | 대시보드 ✍ (초안) → 채팅 `assignment` (다듬기) | ~/report/CLAUDE.md, `bin/pa task <키>` |
| 퀴즈 만들기 | 대시보드 🧩 로 요청 복사 → 채팅 `quiz` | 퀴즈 프로젝트 CLAUDE.md·QUIZ_PLANNING_METHOD.md·과목 PLAN |
| 자료 고르기 (할 일마다) | 대시보드 📄 자료 창 (Claude 안 씀) | config/materials.yaml, docs/usage.md '자료 연결' |
| 규칙 바꾸기 (요일·시간·알림·범위·과목) | 채팅 `rules` — 확인받고 설정 파일만 고침 | config/*.yaml |
| 남은 개발 작업 | docs/TODO.md | |

- 프로그램이 스스로 정하지 못한 것(⚠️ 확인 필요)은 사용자에게 물어 정한다. 규칙은 대화로만 바꾼다.

## git

- 커밋·push 여부와 내 저장소는 `config/profile.md` 의 '내 저장소'를 따른다. 적혀 있지 않으면 커밋만 하고 push 는 묻는다.
- 개인 파일(`config/*.yaml`, `config/profile.md`, `.env`, `data/` 등)은 git 에 넣지 않는다. 설정 견본(`*.example.*`)에는 개인 정보를 넣지 않는다.
- `gh-pages`(휴대폰 화면)·`phone-inbox`(휴대폰 입력) 브랜치는 엔진(`pa/mobile.py`)이 관리한다. 손으로 고치지 않는다.
- 친구용 배포(`personal_assistant_release`, Windows·WSL·리눅스 공용)는 `bin/release`. **사용자가 배포하라고 할 때만** 한다
  (2026-11-16 사용자가 정함 — 평소엔 내 저장소에 커밋·push 만, 배포는 모아서 한 번에). 대신 기능을 바꿀 때마다 `docs/release.md` 의
  점검 목록(개인 정보·견본 설정·OS 공통·Python 3.10·DB 자동 수정·테스트)은 지켜서 언제 배포해도 되는 상태로 두고, 배포 뒤 '배포 기록'에 한 줄.

## 원칙

- 과제 퀴즈를 사용자를 위해 수행 및 제출할 수 있게 돕고, 사용자가 출석할 수 있게 돕는다. 
- 일정·할 일에 관한 답은 추측하지 말고 위 도구를 실행해 얻은 실제 데이터로 한다.
- `.env`, `credentials.json`, `token.json`, `data/` 의 내용은 출력하거나 커밋하지 않는다.
