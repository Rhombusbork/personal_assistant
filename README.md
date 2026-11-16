# Personal Assistant

제주대 Canvas 과제·온라인 강의·시간표를 모아 Google 캘린더에 학습 계획을 짜 주고,
대시보드(http://localhost:8765)로 오늘 할 일을 보여 주는 개인 비서. Claude Code 와 함께 쓰면 공부·보고서 초안도 돕는다.

## 할 수 있는 것

- **할 일 모으기**: Canvas 과제·퀴즈·온라인 강의(실제 길이·출석 마감)를 자동으로, 내 할 일은 대시보드 입력칸이나 `inbox.md` 로
- **자동 계획**: 마감 순으로 빈 시간에 배치해 Google 캘린더 '학습 계획'에 넣는다 (수업·약속은 피함, 하루 한도, 큰 일은 나눔)
- **할 시간 따로 정하기**: `발표 준비 >내일 15-18시 @금` — 15~18시에 하고 마감은 금요일. 수업과 겹치면 회색 안내만 (막지 않음)
- **맨 위 '지금 할 일'**: 진행 중인 계획 > 3시간 안 마감 > **기본 할 일**(급한 게 없을 때 VSCode 폴더나 링크를 버튼 하나로)
- **끝낸 일 자동 체크**: Canvas 제출·강의 수강 완료를 읽어 저절로 사라짐 (곧 마감인 것은 몇 분 안에)
- **마감 직전 촘촘한 알림**(선택): 20분 전부터 2분마다, 같은 때 마감은 하나로 합쳐 휴대폰 Google Calendar 로
- **강의 자료 자동 받기** (LearningX), 공지·새 점수·시험 일정 후보 모아 보기
- **보고서 초안·자료 요약·공지 정리** (Claude Code 또는 Codex, 버튼을 누를 때만)
- **휴대폰 화면**(비밀번호 잠금, GitHub Pages)·휴대폰 입력
- 빠른 입력·inbox 문법 전체: [docs/usage.md](docs/usage.md)

## 처음 설치하기 (다른 사람이 받아 쓸 때)

**필요한 것**: Python 3.10+, git, VSCode, 제주대 Canvas 계정, Google 계정.
컴퓨터는 **Windows 그대로**, **WSL2(Ubuntu)**, **리눅스** 중 아무거나 된다 (Mac 은 시험하지 않음).
선택: AI 하나 — [Claude Code](https://claude.com/claude-code) 또는 [ChatGPT Codex](https://developers.openai.com/codex) (보고서 초안·자료 요약·채팅 비서). 없어도 일정 관리는 다 된다.

**Windows** (PowerShell 또는 명령 프롬프트, [Python](https://www.python.org/downloads/)·[Git](https://git-scm.com/download/win) 먼저 설치):

```powershell
git clone https://github.com/Rhombusbork/personal_assistant_release.git $HOME\personal_assistant
cd $HOME\personal_assistant
bin\setup.cmd     # 파이썬 환경, .env 견본, 빈 폴더를 만들고 남은 일을 알려 줌
```

**WSL2·리눅스**:

```bash
git clone https://github.com/Rhombusbork/personal_assistant_release.git ~/personal_assistant
cd ~/personal_assistant
bin/setup          # 파이썬 환경, .env 견본, 빈 폴더를 만들고 남은 일을 알려 줌
```

> 아래 명령의 `bin/pa` 는 Windows 에서 `bin\pa.cmd` 로 쓴다 (예: `bin\pa.cmd run --full`).

받은 저장소에는 **개인 정보가 하나도 없다**. 설정은 모두 견본(`config/*.example.*`)이고, `bin/setup` 이 이를 내 파일로 복사한다.
내 파일(`.env`, `config/*.yaml`, `config/profile.md`, `credentials.json`, `token.json`, `data/`)은 git 에 올라가지 않는다.

### 1. 비밀 정보 만들기

| 파일 | 무엇 | 만드는 법 |
|---|---|---|
| `.env` | Canvas 토큰 | Canvas → 계정 → 설정 → **새 액세스 토큰** → `.env` 의 `CANVAS_TOKEN=` 뒤에 붙여 넣기 |
| `credentials.json` | Google 캘린더 앱 열쇠 | [docs/google-calendar-setup.md](docs/google-calendar-setup.md) 1~5단계 (내 Google 계정으로) |
| `token.json` | Google 로그인 | 따로 만들지 않음 — 처음 실행할 때 뜨는 주소로 로그인하면 생김 |
| `.env` (선택) | 학교 포털 계정 | `PA_SCHOOL_ID=`·`PA_SCHOOL_PW=` — 강의 플랫폼 로그인이 끊기면 엔진이 자동으로 다시 로그인 (30분에 한 번까지). 평소 브라우저의 강의 로그인이 끊길 수 있음 |

### 2. 내 것으로 채우기 (`예시과목` 을 바꾸기)

- `config/timetable.yaml`: 학기 날짜, 대면 수업 시간표, 온라인 수업(Canvas 과목명), 공부 요일·시간·알림
- `config/courses.yaml`: 과목명 → 자료 폴더 이름 (`~/study_system/materials/<폴더>`)
- `config/profile.md`: 나는 누구인지, 과목 대응표, 내 백업 저장소 (Claude Code 가 읽음)
- `~/report/CLAUDE.md`: 보고서 글쓰기 규칙 (setup 이 견본을 복사) — 0-1 절의 `<학번>`·`<이름>` 을 내 것으로
- Claude Code 를 쓰면 채팅에서 "규칙 바꿔줘"(`rules`)로 해도 된다

### AI: Claude Code 또는 Codex

- 대시보드의 🤖 버튼(보고서 초안·자료 요약·공지 정리)은 `.env` 의 `PA_AI` 로 고른다 (`claude` / `codex`, 비우면 설치된 것).
  어느 쪽이든 **내 구독**으로 돌고, 읽기만 허용한다 (파일은 비서가 쓴다).
- 채팅 비서: Claude Code 는 `CLAUDE.md`·`.claude/skills/`, Codex 는 `AGENTS.md`·`.agents/skills/` 를 읽는다.
  Codex 쪽 파일은 원본(CLAUDE.md·.claude/skills)을 가리키기만 하므로, 규칙은 원본에서만 고친다
  (스킬을 고쳤으면 `python scripts/sync_agents.py`).

### 원래 저장소와 분리

- 이 저장소에서 받은 사람은 원래 저장소에 **쓸 수 없다** (GitHub 권한). 엔진도 원래 주인의 저장소·휴대폰 화면에 접근하지 않는다:
  휴대폰 기능은 `config/mobile.yaml` 의 `repo` 가 비어 있으면 꺼져 있다.
- 내 코드를 백업하려면 GitHub 에 **내 저장소**를 만들고 `git remote set-url origin https://github.com/<나>/<저장소>.git`.
- 휴대폰 화면(선택): 내 public 저장소를 `config/mobile.yaml` 의 `repo`·`pages_url` 에 적고, `.env` 에 `PA_MOBILE_PASSWORD`,
  GitHub 설정 → Pages 에서 `gh-pages` 브랜치를 켠다. 자세한 건 [docs/usage.md](docs/usage.md).

### 실행

```bash
bin/pa sync-timetable        # 수업 시간표를 Google 캘린더에 한 번 넣기
bin/pa run --full             # Canvas → 계획 → 마감 캘린더. 처음엔 Google 로그인 창 주소가 뜸
bin/pa watch                  # 엔진 + 대시보드 http://localhost:8765 (켜 두면 자동 갱신)
```

VSCode 에서 `assistant.code-workspace` 를 열면 엔진과 대시보드가 자동으로 켜진다 ([docs/usage.md](docs/usage.md)).

### 알아 둘 것

- 제주대 전용이다 (`canvas.jejunu.ac.kr`). 다른 학교는 `pa/canvas.py`·`pa/browser.py` 의 주소를 바꿔야 하고, 강의 자료 받기(LearningX)는 동작하지 않을 수 있다.
- 강의 자료 자동 받기는 `bin/pa browser login` 으로 학교 로그인을 한 번 저장해야 된다. `.env` 에 학교 계정을 넣어 두면 끊길 때 자동으로 다시 로그인한다.
- 공부 노트·보고서·퀴즈 연동은 `~/study_system`, `~/report`, `~/quiz_system_project/pharmacy` 폴더를 쓴다. 없으면 그 기능만 비어 있다.
- 내 파일은 절대 공유하지 않는다 (`.env`, `credentials.json`, `token.json`, `data/`).
- 휴대폰 화면·휴대폰 입력은 `git` 명령을 쓴다 (Windows 는 Git for Windows 설치).
- 업데이트: `git pull` → 엔진(대시보드)을 껐다 켠다. 내 설정은 git 밖에 있어서 덮어쓰이지 않는다.
  견본에 새 항목이 생기면 `config/*.example.yaml`·`.env.example` 과 비교해 옮긴다. 데이터베이스(`data/pa.db`)는 엔진이 알아서 고친다.
- `git pull` 이 "unrelated histories"·"diverged" 로 실패하면 (예전 배포 방식으로 받은 경우) 한 번만:
  `git fetch origin && git reset --hard origin/main` — 내 설정·데이터는 git 밖이라 지워지지 않는다. 단 직접 고친 코드는 사라진다.

---

## 목표 (3단계 구현)

1. **일정/할 일 관리**
2. **에이전틱 자동화된 할 일 수행**
3. **컨디션/스트레스 관리**

## 1단계: 일정/할 일 관리 — 관리 대상

| 분류 | 내용 |
|---|---|
| 정기적으로 해야 하는 것 | 과제 및 온라인수업 듣기 |
| 내가 추가하면 기억해줘야 하는 것 | 일정들 (예: 약속, 회의 등) |
| 기록해줘야 하는 것 | 수업시간 |
| 그 외 하고 싶은 일들 | 장기적인 todo로서 기록 |

## 2단계 요구사항 (정리 중)

- 강의 자료(배포용 PDF 등)는 Canvas에서 자동으로 받아 `~/study_system/materials/<영문 과목명>/` 에 모은다 (지금 수동으로 모으는 방식 그대로).
- 공부·보고서·퀴즈 작업은 각각 `~/study_system`, `~/report`, `~/quiz_system_project/pharmacy` 의 규칙을 따른다.
- AI 기능은 API 키 대신 Claude Code 구독(`claude -p`)을 사용한다.

## 장기 요구사항

- 내가 해야 할 일들(마감, 학습 계획, 진행 상황)을 한눈에 보이게 시각화한다. → ✅ TODAY.md · HTML 대시보드 ([docs/usage.md](docs/usage.md))
- 매일의 일정 관리는 Claude 없이 코드로 동작한다 (inbox.md 입력 → 자동 계획·기록·시각화). 설계: [docs/automation-plan.md](docs/automation-plan.md)
- 휴대폰: GitHub Pages (비밀번호 잠금, 휴대폰 입력 → PC 반영) — `config/mobile.yaml`
- 종합 설계(욕구 분석·제안 기능·가능/불가능·로드맵): [docs/assistant-master-design.md](docs/assistant-master-design.md)

## 진행 상황

- [x] 1단계: 일정/할 일 관리 (시간표·Canvas 과제·학습 계획 → Google Calendar)
- [~] 2단계: 에이전틱 자동화된 할 일 수행 — 자료 자동 다운로드·수강 확인·보고서 초안·자료 요약·공지 정리·퀴즈 복습·시험 일정 후보·할 일별 자료 연결 (R1~R8, R10, R11 완료)
- 남은 일·막힌 것·사용자가 할 일: [docs/TODO.md](docs/TODO.md) · 채팅 작업 지침: [CLAUDE.md](CLAUDE.md) "무엇을 어디서"
- [ ] 3단계: 컨디션/스트레스 관리 (보류)
