# 친구용 배포 (release) 절차

내 저장소(`personal_assistant`, 개발용)의 지금 코드를 배포 저장소(`personal_assistant_release`)에 올리는 일.
받은 사람은 **Windows 그대로 / WSL2 / 리눅스** 어디서든 `git clone` → `bin/setup` → 내 설정 채우기로 쓴다.
기능을 바꿀 때마다 아래 **점검 목록**을 같이 지키면, 배포할 때 따로 고칠 것이 없다.

언제: **사용자가 배포하라고 할 때만** (평소엔 내 저장소에 커밋·push). `bin/release` 는 지난 배포 이후 바뀐 것을 한 번에 올리므로
모아서 배포해도 빠지는 것은 없다. 배포할 때 볼 것: 아래 '배포 기록'의 마지막 원본 커밋 이후 `git log --oneline <그 커밋>..HEAD`.

## 한눈에

```bash
git status                  # 깨끗해야 함 (커밋 안 된 건 안 나감)
git push                    # 내 저장소에 먼저
bin/release --dry-run       # 검사 + 바뀌는 파일 목록만 (올리지 않음)
bin/release                 # 올림
```

`bin/release` 가 알아서 하는 것: 커밋 안 된 변경 확인 → 개인 정보 검사 → 테스트 → 배포 저장소의 **이전 배포 커밋 위에**
지금 파일로 한 커밋 → 일반 push. Windows 에서는 Git Bash 로 실행한다.

## 무엇이 나가고 무엇이 안 나가나

| 나감 | 안 나감 (절대) |
|---|---|
| git 에 커밋된 파일 (HEAD 그대로) | `.env`, `credentials.json`, `token.json`, `data/`(DB·로그인 상태), `config/*.yaml`, `config/profile.md`, `inbox.md`, `TODAY.md`, `dashboard/data.js`, `추가자료/` (.gitignore) |
| 배포마다 커밋 하나 (`Release 날짜 (원본 커밋)`) | 내 개발 커밋 기록·메시지, `bin/release` 자신 |

`~/report`, `~/study_system`, `~/quiz_system_project` 는 이 저장소 밖이라 처음부터 안 나간다.
`~/report/CLAUDE.md` 는 `templates/report-CLAUDE.md` 견본으로만 나간다 (학번·이름 자리는 `<학번>`·`<이름>`).

## 기능을 바꿀 때마다 지킬 것 (점검 목록)

### 1. 개인 정보는 코드·문서에 쓰지 않는다
- [ ] 아이디·학번·이름·집 경로(`/home/<나>/…`)·이메일·내 GitHub 저장소 주소를 코드나 문서 예시에 쓰지 않는다.
  예시는 `<학번>`, `~/report`, `예시과목` 처럼 쓴다. (`bin/release` 가 내 아이디, 학번 문장, `숫자10자리_` 파일명, 집 경로 등을 잡지만 전부는 못 잡는다)
- [ ] 개인 값이 필요하면 `.env` 또는 `config/*.yaml` 에서 읽고, **견본**(`.env.example`, `config/*.example.yaml`)에는 빈 값·설명만.
- [ ] 개인 상태(로그인, 기본 할 일 목록, 하기 날짜 등)는 `data/pa.db` 의 meta 나 표에 둔다 — git 밖.

### 2. 새 설정이 생기면 받는 사람도 알 수 있게
- [ ] `.env.example` 에 주석과 함께 추가 (선택 항목은 `# KEY=` 로 꺼 둔 채).
- [ ] `config/*.example.yaml` 에 기본값 추가, 코드는 값이 없어도 돌아가게 (`.get(..., 기본값)`).
- [ ] 새 견본 파일이면 `scripts/setup.py` 가 복사하게 하고, README '1. 비밀 정보 만들기'·'2. 내 것으로 채우기' 표에 한 줄.
- [ ] 다른 저장소 규칙 파일(`~/report/CLAUDE.md` 등)을 바꿨으면 `templates/` 견본에도 같은 내용 (개인 값은 자리표시로).

### 3. Windows·WSL·리눅스 모두에서 돌게
- [ ] 경로는 `pathlib.Path` · `Path.home()` 로. `/home/…`, `/mnt/c/…`, `C:\…` 를 코드에 박지 않는다.
- [ ] 브라우저로 열기·탐색기·다운로드 폴더는 `pa/osutil.py` (`open_url`, `reveal`, …) 만 쓴다. VSCode 열기는 `pa/materials.py` 의 `_vscode_open`.
- [ ] 파일 읽기·쓰기는 `encoding="utf-8"` 을 꼭 적는다 (Windows 기본값은 cp949).
- [ ] 셸 문법(`|`, `&&`, `sh -c`)에 기대는 subprocess 를 쓰지 않는다. 명령은 리스트로.
- [ ] 새 `bin/pa` 명령은 `bin/pa`(sh)와 `bin/pa.cmd` 둘 다에서 되는지 (둘 다 `python -m pa` 로 넘기는지) 확인.
- [ ] **Python 3.10** 문법으로 (README 최소 버전): f-string `{}` 안에 백슬래시 금지(3.12 부터만 됨), `tomllib`·`except*` 등 3.11+ 기능 금지.
  점검: `grep -rnE "f\"[^\"]*\{[^}]*\\\\" pa/` 처럼 f-string 안 백슬래시 찾기.
- [ ] Playwright(LearningX 로그인)는 `PLAYWRIGHT_BROWSERS_PATH` 가 없어도 기본 위치로 동작해야 한다.

### 4. 데이터베이스가 바뀌면 자동으로 고쳐지게
- [ ] 새 표는 `pa/db.py` 의 `SCHEMA` (`CREATE TABLE IF NOT EXISTS`).
- [ ] 기존 표에 칸 추가는 `db.connect()` 에서 `PRAGMA table_info` 로 확인 후 `ALTER TABLE … ADD COLUMN` (예: `tasks.slot_end`).
  받은 사람에게 "data/ 를 지우세요" 를 시키지 않는다.

### 5. 규칙·문서
- [ ] `CLAUDE.md` 나 `.claude/skills/` 를 바꿨으면 `python scripts/sync_agents.py` (Codex 쪽 `.agents/skills`).
- [ ] 사용법은 `docs/usage.md`, 큰 기능은 README '할 수 있는 것' 에 한 줄, 남은 일은 `docs/TODO.md`.
- [ ] 받은 사람이 해야 하는 일이 생겼으면 (새 설정, 다시 로그인 등) README '업데이트' 부분에.

### 6. 시험
- [ ] `.venv/bin/python -m pytest -q tests` 통과 (새 문법·계산은 테스트 한 개 이상 추가).
- [ ] 테스트는 진짜 외부 서비스(학교 로그인·Canvas·Google·GitHub)를 부르지 않는다 — 새로 그런 코드를 넣으면 `tests/conftest.py` 에서 막는다.
- [ ] 대시보드를 바꿨으면 브라우저 콘솔에 오류가 없는지. node 가 없으면 Playwright 로:
  `dashboard/index.html` 을 `file://` 로 열고 `pageerror` 를 모아 보기 (data.js 는 `bin/pa run` 으로 새로).
- [ ] 엔진(`bin/pa watch`)을 다시 켜서 실제로 한 번 눌러 보기 — 서버 코드는 다시 켜야 반영된다.

## 배포 후 확인

```bash
cd "$(mktemp -d)" && git clone -q https://github.com/Rhombusbork/personal_assistant_release.git r && cd r
git log --oneline | head -3          # 맨 위가 방금 배포
python3 -m venv .venv && .venv/bin/pip -q install -r requirements.txt && .venv/bin/python -m pytest -q tests
```

- 받은 사람이 업데이트하는 법: `git pull` → 엔진 다시 켜기 (README '알아 둘 것').

## 겪었던 문제 (다시 안 겪게)

| 날짜 | 문제 | 지금 |
|---|---|---|
| 2026-11-16 | 배포마다 기록 없는 새 커밋을 **강제 push** → 받은 사람의 `git pull` 이 "unrelated histories" 로 실패 | 이전 배포 커밋 위에 쌓고 일반 push. 예전에 받은 사람은 한 번 `git fetch origin && git reset --hard origin/main` |
| 2026-11-16 | f-string 안 백슬래시 — 개발 PC(3.12)에서는 되지만 3.10 에서 문법 오류 | 정규식은 함수로 빼서 씀 (`render._plain`). 점검 목록 3 |
| 2026-11-16 | 자동 로그인을 넣은 뒤, '로그인 끊김'을 흉내 내는 테스트가 `.env` 의 실제 계정으로 **진짜 학교 로그인**을 함 (테스트 돌릴 때마다) | `tests/conftest.py` 가 모든 테스트에서 자동 로그인을 막고, `browser.auto_login` 도 테스트 중이면 거부 |
| 2026-11-16 | 개발 중 파일을 두 번에 나눠 고치는 사이 엔진이 덜 고친 코드로 스스로 다시 시작 → 감시 루프 오류로 엔진이 꺼짐 | 다시 시작 전 새 코드를 다른 프로세스에서 import 해 보고, 루프는 오류가 나도 계속 (`pipeline._new_code_ok`) |
| 2026-11-16 | 보고서 폴더를 과목별로 나눴더니 대시보드가 기존 보고서를 못 찾음 | `jobs.report_path` 가 `~/report` 아래 전체에서 찾음. 견본 `templates/report-CLAUDE.md` 에도 규칙 추가 |

## 배포 기록

| 날짜 | 원본 커밋 | 주요 변경 |
|---|---|---|
| 2026-11-16 | 9f4f77d | 할 시간·마감 분리, 기본 할 일, 할 시간 겹침 안내, LearningX 자동 로그인, 보고서 과목 폴더, 배포 방식(이전 배포 위에 쌓기) |
| 2026-11-16 | f743772 | 기본 할 일 폴더 자동 완성(VSCode 최근·git 저장소·Tab), 마감 직전 촘촘한 알림(합치기, 견본은 꺼짐), 곧 마감인 것 제출·수강 빠른 확인 |
| 2026-11-16 | 6ac9813 | 켤 때마다 Canvas 확인(창 먼저), canvas.check_every_hours 설정, 엔진 오류 내성(덜 고친 코드로 재시작 안 함), 대시보드 중복 창 안내 |
| 2026-11-16 | ea189b5 | 켤 때 창이 뜬 뒤 최신화 시작, 상태 줄 '최신화 중' |
| 2026-11-16 | 9319b82 | 창 늘 하나(없으면 3분 뒤 앱 창, 오늘은 끄기), 로그인할 때 엔진(작업 스케줄러 Engine), bin/pa open·shortcut, 자동 로그인 직전 .env 다시 읽기 |
| 2026-11-16 | 2427800 | 대시보드 VSCode 안 탭(비서 확장, dashboard.mode), 로그인 때 VSCode 열기, 테스트가 진짜 로그인하지 않게, 하루 3번 실행은 켜진 엔진에 맡김 |
