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

그다음 비밀 정보 세 가지를 **직접 만든다**. 이 파일들은 git 에 올라가지 않으므로 저장소에는 없다.

| 파일 | 무엇 | 만드는 법 |
|---|---|---|
| `.env` | Canvas 토큰 | Canvas → 계정 → 설정 → **새 액세스 토큰** → `.env` 의 `CANVAS_TOKEN=` 뒤에 붙여 넣기 |
| `credentials.json` | Google 캘린더 앱 열쇠 | [docs/google-calendar-setup.md](docs/google-calendar-setup.md) 1~5단계 |
| `token.json` | Google 로그인 | 따로 만들지 않음 — 처음 실행할 때 뜨는 주소로 로그인하면 생김 |

### 내 것으로 바꾸기

저장소에는 원래 주인의 설정이 들어 있다. 실행 전에 바꾼다.

- `config/timetable.yaml`: 학기 날짜, 대면 수업 시간표, 온라인 수업 이름, 공부 요일·시간
- `config/courses.yaml`: 과목명 → 자료 폴더 이름 (`~/study_system/materials/<폴더>`)
- `CLAUDE.md`: 맨 위의 '사용자' 소개와 과목 대응표 (Claude Code 가 읽는 규칙)
- **휴대폰 화면은 처음엔 꺼져 있다.** 켜려면 자기 GitHub 저장소를 만들어 `config/mobile.yaml` 의 `repo`·`pages_url` 을 바꾸고,
  그다음 `.env` 에 `PA_MOBILE_PASSWORD` 를 넣는다. 주소를 바꾸지 않고 켜면 원래 주인의 저장소로 올리려다 실패한다

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
- `.env`, `credentials.json`, `token.json`, `data/` 는 절대 공유하거나 커밋하지 않는다.
- 업데이트: `git pull`. 바꾼 설정 파일과 겹치면 git 이 알려 준다. 그때 내 값을 지키면 된다.

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
- 휴대폰: https://rhombusbork.github.io/personal_assistant/ (비밀번호 잠금, 휴대폰 입력 → PC 반영)
- 종합 설계(욕구 분석·제안 기능·가능/불가능·로드맵): [docs/assistant-master-design.md](docs/assistant-master-design.md)

## 진행 상황

- [x] 1단계: 일정/할 일 관리 (시간표·Canvas 과제·학습 계획 → Google Calendar)
- [~] 2단계: 에이전틱 자동화된 할 일 수행 — 자료 자동 다운로드·수강 확인·보고서 초안·자료 요약·공지 정리·퀴즈 복습·시험 일정 후보·할 일별 자료 연결 (R1~R8, R10, R11 완료)
- 남은 일·막힌 것·사용자가 할 일: [docs/TODO.md](docs/TODO.md) · 채팅 작업 지침: [CLAUDE.md](CLAUDE.md) "무엇을 어디서"
- [ ] 3단계: 컨디션/스트레스 관리 (보류)
