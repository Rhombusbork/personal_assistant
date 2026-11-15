# Personal Assistant

제주대 Canvas 과제·온라인 강의·시간표를 모아 Google 캘린더에 학습 계획을 짜 주고,
대시보드(http://localhost:8765)로 오늘 할 일을 보여 주는 개인 비서. Claude Code 와 함께 쓰면 공부·보고서 초안도 돕는다.

## 처음 설치하기 (다른 사람이 받아 쓸 때)

**필요한 것**: Linux 또는 WSL2(Ubuntu), Python 3.10+, git, 제주대 Canvas 계정, Google 계정.
선택: [Claude Code](https://claude.com/claude-code) (보고서 초안·자료 요약·채팅 비서), VSCode.

```bash
git clone https://github.com/Rhombusbork/personal_assistant.git ~/personal_assistant
cd ~/personal_assistant
bin/setup          # 파이썬 환경, .env 견본, 빈 폴더를 만들고 남은 일을 알려 줌
```

받은 저장소에는 **개인 정보가 하나도 없다**. 설정은 모두 견본(`config/*.example.*`)이고, `bin/setup` 이 이를 내 파일로 복사한다.
내 파일(`.env`, `config/*.yaml`, `config/profile.md`, `credentials.json`, `token.json`, `data/`)은 git 에 올라가지 않는다.

### 1. 비밀 정보 만들기

| 파일 | 무엇 | 만드는 법 |
|---|---|---|
| `.env` | Canvas 토큰 | Canvas → 계정 → 설정 → **새 액세스 토큰** → `.env` 의 `CANVAS_TOKEN=` 뒤에 붙여 넣기 |
| `credentials.json` | Google 캘린더 앱 열쇠 | [docs/google-calendar-setup.md](docs/google-calendar-setup.md) 1~5단계 (내 Google 계정으로) |
| `token.json` | Google 로그인 | 따로 만들지 않음 — 처음 실행할 때 뜨는 주소로 로그인하면 생김 |

### 2. 내 것으로 채우기 (`예시과목` 을 바꾸기)

- `config/timetable.yaml`: 학기 날짜, 대면 수업 시간표, 온라인 수업(Canvas 과목명), 공부 요일·시간·알림
- `config/courses.yaml`: 과목명 → 자료 폴더 이름 (`~/study_system/materials/<폴더>`)
- `config/profile.md`: 나는 누구인지, 과목 대응표, 내 백업 저장소 (Claude Code 가 읽음)
- Claude Code 를 쓰면 채팅에서 "규칙 바꿔줘"(`rules`)로 해도 된다

### 원래 저장소와 분리

- 이 저장소에서 받은 사람은 원래 저장소에 **쓸 수 없다** (GitHub 권한). 엔진도 원래 주인의 저장소·휴대폰 화면에 접근하지 않는다:
  휴대폰 기능은 `config/mobile.yaml` 의 `repo` 가 비어 있으면 꺼져 있다.
- 내 코드를 백업하려면 GitHub 에 **내 저장소**를 만들고 `git remote set-url origin https://github.com/<나>/<저장소>.git`.
- 휴대폰 화면(선택): 내 public 저장소를 `config/mobile.yaml` 의 `repo`·`pages_url` 에 적고, `.env` 에 `PA_MOBILE_PASSWORD`,
  GitHub 설정 → Pages 에서 `gh-pages` 브랜치를 켠다. 자세한 건 [docs/usage.md](docs/usage.md).

### 실행

```bash
python -m pa.sync_timetable   # (.venv 안에서) 수업 시간표를 Google 캘린더에 한 번 넣기
bin/pa run --full             # Canvas → 계획 → 마감 캘린더. 처음엔 Google 로그인 창 주소가 뜸
bin/pa watch                  # 엔진 + 대시보드 http://localhost:8765 (켜 두면 자동 갱신)
```

VSCode 에서 `assistant.code-workspace` 를 열면 엔진과 대시보드가 자동으로 켜진다 ([docs/usage.md](docs/usage.md)).

### 알아 둘 것

- 제주대 전용이다 (`canvas.jejunu.ac.kr`). 다른 학교는 `pa/canvas.py`·`pa/browser.py` 의 주소를 바꿔야 하고, 강의 자료 받기(LearningX)는 동작하지 않을 수 있다.
- 강의 자료 자동 받기는 `bin/pa browser login` 으로 학교 로그인을 한 번 저장해야 된다.
- 공부 노트·보고서·퀴즈 연동은 `~/study_system`, `~/report`, `~/quiz_system_project/pharmacy` 폴더를 쓴다. 없으면 그 기능만 비어 있다.
- 내 파일은 절대 공유하지 않는다 (`.env`, `credentials.json`, `token.json`, `data/`).
- 업데이트: `git pull`. 내 설정은 git 밖에 있어서 덮어쓰이지 않는다. 견본에 새 항목이 생기면 `config/*.example.yaml` 과 비교해 옮긴다.

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
