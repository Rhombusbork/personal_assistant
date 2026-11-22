# 주차별 시간표 · 예약 · 자동 제출 (계획)

> 작성 2026-11-22 · 상태: **조사·계획**. 지금 [주차별]은 날짜별 목록 (`dashboard/index.html` 의 `weekView`).
> 목표: 대학 시간표 앱처럼 월~일 × 시간 칸으로 한 주를 보여 주고, 계획 블록을 끌어서 옮긴다.

## 1. 정한 것 (사용자 요청)

- 한 주를 **시간표 모양**으로 (요일 = 세로 칸, 시간 = 가로 줄, 일정 = 색 블록)
- **보이는 시간 범위는 일정에 맞춘다**: 그 주에서 가장 이른 일정의 시작 ~ 가장 늦은 일정의 끝.
  03시에 시작하는 게 있으면 03시부터, 10시부터면 10시부터.
- 크기 적당히, 넘치면 **스크롤**
- **끌어서 옮기기**는 실수로 안 움직이게 **작은 손잡이(⠿)** 로만 (2026-11-22 확정)

## 2. 조사한 디테일 (출처는 맨 아래)

### 2-1. 시간 범위·격자
- 범위 = 그 주의 `min(시작)` 을 **정시로 내림**, `max(끝)` 을 **정시로 올림**. 위아래로 30분씩 여유를 두면 블록이 테두리에 붙지 않는다.
- 일정이 하나도 없는 주는 기본 범위(예: 09~18시)를 보여 준다.
- 큰 달력 앱(구글 캘린더 등)은 자동으로 범위를 줄이는 기능이 **없다** — 사용자들이 계속 요청하는 기능 (Airtable·ClickUp·GNOME·Confluence 요청 글). 이 화면만의 장점이 된다.
- 다만 **새벽 3시 일정 하나** 때문에 03~10시가 빈 칸이 될 수 있다 → 빈 시간 덩어리(예: 3시간 넘게 아무것도 없음)는 **얇은 접힌 띠**("05–09시 비어 있음")로 줄이는 방법. 첫 버전은 범위만, 접기는 나중.
- 드래그 중에는 범위 밖으로도 옮길 수 있게 **위아래로 1시간씩 넓혀** 보여 준다.
- 정시 = 진한 선, 30분 = 옅은 점선. 왼쪽에 시각 숫자(09, 10…).
- 위쪽 **요일 머리줄**과 왼쪽 **시각 열은 스크롤해도 고정**(sticky).
- **지금 시각 빨간 선**은 오늘 칸에만, 1분마다 움직임. 처음 열 때 지금 시각이 보이게 스크롤.
- 오늘 칸은 머리줄을 강조, 지나간 시간은 블록을 흐리게.
- 하루 종일 일정(시험일 등)·시간 없는 마감은 시간 칸 위의 **'종일' 줄**에 작게.

### 2-2. 블록 모양
- 보여 준 사진처럼: **과목 이름 굵게 + 강의실/설명 작게**, 과목마다 고정 색.
- **종류 구분**: 수업(🏫, 옮길 수 없음)은 꽉 찬 색, 비서가 짠 계획 블록은 옅은 색 + 테두리, 직접 정한 고정 블록은 📌.
- **짧은 블록**(30분 이하): 높이가 한 줄도 안 되면 글자가 잘린다 → 최소 높이 한 줄, 짧으면 "제목 · 시각"을 한 줄로 (FullCalendar 는 30px 아래를 '짧은 블록' 모양으로 바꿈).
- 글자는 넘치면 말줄임(…), 마우스를 올리면 전체(제목·시각·마감·이유).
- **겹치는 일정**: 나란히 둘로 나눔(가장 흔함). 셋 이상 겹치면 읽기 어려움 → 칸을 나누고 블록에 살짝 틈과 테두리.
- **색 대비**: 밝은 파스텔 바탕엔 진한 글자, 다크 모드에선 어둡고 채도 낮은 바탕 + 밝은 글자. 다크 모드에서 같은 색을 그대로 쓰면 글자가 안 읽힘 (Mozilla·Discourse 버그). 글자색은 바탕 밝기로 정한다(4.5:1).

### 2-3. 끌어서 옮기기
- **손잡이로만**: 블록 오른쪽 위 작은 ⠿. 블록 몸통을 누르면 지금처럼 메뉴·열기. 손잡이에만 `touch-action: none` 을 걸어야 휴대폰에서 블록 위로도 스크롤된다.
- **휴대폰**: 브라우저는 누르는 순간 스크롤할지 정해서, '꾹 누르고 끌기'와 스크롤이 부딪힌다 → 손잡이는 바로 끌기, 몸통은 스크롤.
- 클릭과 끌기 구분: **5px** 넘게 움직여야 끌기 시작.
- **15분 단위로 맞춤**(snap). 대부분의 달력이 기본 15분.
- **그림자 미리보기**: 놓일 자리에 블록 길이 그대로의 반투명 그림자 + 바뀔 시각 표시("수 14:15–15:45"). GNOME·KDE 달력은 그림자가 첫 15분만 표시돼서 버그로 고침 → **길이 전체**를 보여 준다.
- 다른 요일 칸으로 옆으로 끌면 날짜도 바뀜.
- **Esc** 로 끌기 취소.
- 화면 끝 근처(약 40px)에 가면 **자동 스크롤**, 끝에 가까울수록 빠르게.
- **겹쳐 놓기 허용** (2026-11-22 사용자가 정함): 한 시간에 두 일을 넣을 수 있다 (예: 강의 틀어 두고 과제).
  수업 위에 놓으면 그림자에 "수업과 겹침"만 작게 보이고 막지 않는다. 겹친 블록은 나란히 반씩.
  비서의 **자동 배치는 지금처럼 빈 시간에만** 넣는다 — 겹침은 사용자가 손으로 놓을 때만.
- **놓자마자 화면에 반영**(기다리지 않음) + 아래에 "옮김 · **되돌리기**" 알림 몇 초. 끌기는 원래 자리가 화면에서 사라지는 유일한 동작이라 되돌리기가 중요.
- 연달아 빨리 두 번 옮겨도 첫 번째가 되돌려지지 않게 (KDE 달력 버그) — 요청마다 따로 처리.
- **옮긴 블록은 고정**: 옮긴 뒤 비서가 다시 계획을 짤 때 그 블록은 그대로, 나머지가 피해 간다 (자동 배치 앱 Motion 은 다 다시 섞어서 "엉망 같다"는 후기, Sunsama·Akiflow 는 손으로 정한 것을 지킴).
- **끌기 없이도 옮길 수 있게**(웹 접근성 WCAG 2.5.7): ⋯ 메뉴의 "시간 바꾸기" → 요일·시각 고르기. 키보드도: 블록 고르고 ↑↓ 15분, ←→ 하루.
- (나중) 아래 끝을 끌어 **길이 바꾸기**. 옮기기와 헷갈리지 않게 손잡이를 따로 (Ashby 는 길이 손잡이를 오른쪽으로 옮겨 실수를 줄임).

### 2-4. 좁은 화면
- 휴대폰 세로에서 7칸은 너무 좁다 → **월~금만** 또는 **3일씩** + 좌우로 넘기기. 주말 칸은 그 주에 일정이 있을 때만 보이기.
- VSCode 탭을 반으로 나눈 좁은 폭도 같은 규칙.

## 3. 이 비서에 맞추기

| 블록 | 어디서 옴 | 옮길 수 있나 |
|---|---|---|
| 수업·약속 | `D.busy` (Google 캘린더·포털 시간표) | ❌ 손잡이 없음 |
| 비서가 짠 계획 | `D.plan` | ✅ 옮기면 고정 블록이 됨 |
| 직접 정한 할 시간 | `D.plan` 의 `…#고정` (inbox 의 할 시간) | ✅ 시간만 바꿈 |
| 이미 지난 블록 | | ❌ |

- 저장: 이미 있는 **"직접 정한 할 시간"(`#고정`, `pa/plan.py`)** 을 그대로 쓴다.
  새 `POST /api/move {key, start, end}` → inbox 할 일이면 그 줄의 할 시간을 고치고, Canvas 항목이면 `tasks` 의 earliest·slot_end 를 적는다 → 계획 다시 짜기 → 캘린더 반영.
- 되돌리기: `POST /api/move` 에 옛 시각을 다시 보냄 (원래 자동 블록이었으면 고정 풀기).
- 휴대폰 화면(`gh-pages`)은 엔진을 거쳐 늦게 반영되므로 **첫 버전은 PC 대시보드에서만 끌기**, 휴대폰은 보기만.
- 목록 보기(지금 화면)는 버튼 하나로 오갈 수 있게 남긴다 ([시간표 | 목록]).

## 3-1. 주차별에서 AI·자동 작업 예약 (사용자 요청 2026-11-22)

지금은 계획 블록이 시작될 때 **종류에 따라 정해진 것만** 연다 (`pa/autoopen.py`: 강의 → 페이지 + ▶, 퀴즈 → 퀴즈 페이지,
과제 → 3시간 전 초안 + 제출 페이지). **시간을 고를 수도, 할 동작을 고를 수도 없다** — Canvas·강의 항목은 '할 시간'을
정하는 길이 없고(inbox 할 일만 `>` 로 가능), 계획기가 정한 시각에만 열린다.

주차별에서 빈 칸을 누르거나 블록의 ⋯ → **"예약"** 창:

| 칸 | 고르는 것 |
|---|---|
| 무엇을 | 할 일 하나 (강의·과제·퀴즈·inbox) 또는 '그냥 AI 작업' |
| 언제 | 요일·시작·끝 (15분 단위), 반복 (매주 같은 요일) |
| 시작할 때 | ☐ 강의 열기 ☐ ▶ 재생 ☐ 퀴즈 페이지 ☐ 초안 파일·탐색기 ☐ Canvas 제출 페이지 ☐ VSCode 작업 창 — 종류에 맞는 것이 기본으로 체크 |
| 미리 (AI) | ☐ 보고서 초안 ☐ 자료 요약 ☐ 공지 정리 — 몇 시간 전 (기본 3) |
| 알림 | 휴대폰 몇 분 전 (기본 10·0) |
| 늦게 깼을 때 | 몇 분까지 열지 (기본 15) |

- 예약 블록에는 아이콘을 붙인다 (▶ 재생 · ✍ 초안 · 📄 요약) → 시간표에서 "이때 비서가 뭘 하는지" 보인다.
- 저장: 할 시간은 `tasks.earliest/slot_end` (Canvas 항목도 — Canvas 확인이 덮어쓰지 않게), 동작은 새 표 `schedule_actions(plan_key, action, offset)`.
  `pa/autoopen.py` 는 블록의 동작 목록이 있으면 그것만, 없으면 지금처럼 종류 기본값.
- AI 작업은 지금처럼 `pa/jobs.py` 대기열에 넣는다 (정해진 시각에). 구독 사용량을 쓰므로 창에 "AI 씀" 표시.
- 겹친 두 블록이 같은 시각에 시작하면 둘 다 연다 (재생은 하나만 — 소리 겹침 방지, 먼저 놓은 것).

## 3-2. 예약 두 가지 (사용자 요청 2026-11-22 — 3-1 을 쉽게)

**쉬운 예약 = 시간만 정하면 끝.** 블록을 끌어 놓거나 "시간 정하기"만 하면 그 일의 종류에 맞는 일을 다 한다.

| 종류 | 미리 | 시작할 때 | 끝날 때 |
|---|---|---|---|
| 강의 | 자료 PDF 받아 두기 | 강의 페이지 + ▶ 재생 + 노트 파일 | LearningX 로 다 들었는지 확인 → 완료 / 덜 들었으면 남은 시간 다시 배치 |
| 보고서·과제 | N시간 전 AI 초안 (✍ 와 같은 작업) | 초안 + 탐색기 + Canvas | (제출 설정에 따라) 3-3 |
| 퀴즈 | | 퀴즈 페이지 + 퀴즈 도움 | 제출됐는지 확인 |
| 퀴즈 복습 | | 퀴즈 앱 | |

**고급 예약 = "+ 예약 추가"** (할 일과 따로, 아무 칸에):
- **AI 에게 프롬프트**: 직접 쓴 지시 + 작업 폴더(study_system·report·hra…) + 결과를 어디에 둘지 → 그 시각에 `pa/jobs.py` 대기열 (claude -p / codex). 예) "토 9시: 이번 주 생화학 노트로 퀴즈 10문제"
- **만들어 둔 기능 고르기**: 강의 열기·재생 / 보고서 초안 / 자료 요약 / 공지 정리 / Canvas 전체 확인 / 시간표 읽기 / 기본 할 일 열기 / 링크·폴더 열기
- 반복(매주·매일), 결과 알림(대시보드·휴대폰)
- 저장: 새 표 `schedules(id, start, end, every, action, args_json, task_key?)`. 엔진의 30초 감시가 시각이 되면 실행 → `events` 에 기록. 실패하면 대시보드에 ⚠️.

## 3-3. 자동 제출 (Canvas API — 2026-11-22 손으로 한 번 성공: 파일 올리기 3단계 → 제출)

- 보낼 파일: 보고서 .md → PDF (`pa/pdf.py`), 이름은 report 규칙대로. **.md 는 절대 안 보냄** (12주차 결과보고서를 .md 로 낸 실수).
- 제출 전 확인 (하나라도 걸리면 안 냄): 제출 방식이 파일 올리기인지, 남은 횟수(`allowed_attempts`), 허용 확장자,
  잠김(`lock_at`·`locked_for_user`), 파일이 있는지, 이미 낸 파일과 이름·크기가 같은지(같으면 "이미 냄"), .md 가 PDF 보다 새것이면 PDF 다시 만들기.
- 제출 뒤 확인: Canvas 에서 다시 읽어 파일 이름·크기·몇 번째 제출인지 맞는지 → `events` 에 `submitted` 기록 →
  **PC: 탐색기에서 그 파일 선택해 보여 주기** / **휴대폰: 대시보드 '제출 기록'에 파일·크기·쪽수·몇 번째·Canvas 링크** (gh-pages 데이터에 들어감).
- 제출 방식 (과제마다, 기본은 ①):
  1. **확인 후 제출** — 준비가 되면 휴대폰·대시보드에 "PDF 3쪽 · 제출할까요? [제출] [열어 보기]"
  2. **완성 표시한 것만 자동** — 보고서에 ✅ 완성 표시를 한 것만, 예약 시각에 자동 제출
  3. **마감 안전망** — 마감 N시간 전까지 안 냈으면 ✅ 완성본을 자동 제출 (완성 표시 없으면 알림만)
- AI 가 쓴 초안을 사람이 보지 않고 바로 내는 건 막는다 (완성 표시 필요).

## 3-5. PC 전원 (원격 조종 · 절전) — 2026-11-22 이 노트북으로 확인

이 노트북(LG 그램, 2017)은 **옛날식 절전(S3)** 을 쓴다 → 예약 깨우기가 Modern Standby 보다 잘 되는 편.
Wi-Fi 카드(Intel 8265)는 **'깨우기 가능 장치'** 이고 드라이버에 **Wake on 매직 패킷 · 패턴 일치가 켜져 있음**.
지금 '절전 해제 타이머 허용'은 충전 중 = **중요 타이머만**, 배터리 = **사용 안 함** → 예약 깨우기를 하려면 충전 중 '사용'으로 (사용자 허락 후).

| 방법 | 언제 | 할 것 | 확인 |
|---|---|---|---|
| ① **예약 깨우기** (기본) | 자기 전에 "이때 켜져 있어" | 작업 스케줄러 '컴퓨터 깨우기' 작업 + 깨운 뒤 그 시간 동안 절전 막기 | 덮개 닫고 2분 뒤 깨우기 시험 (`powercfg /waketimers`) |
| ② **Wi-Fi 매직 패킷** | 집 Wi-Fi 안에서 휴대폰으로 지금 | 휴대폰 WoL 앱 → 이 PC 의 Wi-Fi MAC | 집에서 한 번 시험 (충전 중·덮개 닫고) |
| ②-1 밖에서 | 집 밖에서 지금 | 공유기의 원격 켜기(WOL) 기능(예: ipTIME 앱) 또는 다른 노트북(대기 PC)이 깨어 있으면 그 PC 가 매직 패킷을 대신 보냄 (휴대폰 → Tailscale → 대기 PC) | ② 가 되면 |
| ③ 주기적으로 잠깐 깨기 | ①② 가 안 될 때 | 30분마다 깨어 휴대폰 [☀️ 깨어 있어] 확인 → 없으면 다시 절전 (충전 중만) | |
| 💤 휴대폰으로 재우기 | PC 가 깨어 있을 때 | 휴대폰 [💤 절전] → 엔진이 절전 (진행 중 작업이 끝난 뒤) | |

- Wi-Fi 로 깨우기는 **절전(S3)에서만**, 최대 절전(최대 절전 모드·종료)에서는 안 된다. 같은 공유기에 붙어 있어야 한다.
- Remote Control 은 깨면 다시 이어진다 (claude 가 계속 켜져 있으면). 깨어 있는데 인터넷이 10분 넘게 끊기면 끝남.
- MAC 주소 같은 이 PC 정보는 `config/power.yaml`(git 제외)에, 견본에는 빈 값.

## 4. 예약·자동 제출 구현 계획 (단계별 — 각 단계가 끝나면 쓸 수 있음)

| 단계 | 만드는 것 | 파일 | 끝나면 되는 것 |
|---|---|---|---|
| **P1 제출 기반** ✅ 2026-11-22 | `pa/submit.py` (제출 전 확인 · PDF 만들기 · 올리기 · 다시 읽어 확인 · 기록), `bin/pa submit <키> [파일] [--yes]`, 제출 뒤 탐색기, 대시보드·휴대폰 '제출 기록' | `pa/submit.py`, `pa/canvas.py`, `pa/__main__.py`, `pa/render.py`, `dashboard/index.html`, `tests/test_submit.py` | 채팅·명령으로 안전하게 제출, 휴대폰에서 낸 파일 확인 |
| **P2 제출 버튼** ✅ 2026-11-23 | 과제 줄 ⋯ → [📤 제출] (확인 창: 파일·쪽수·몇 번째·마감) · 휴대폰 [제출] (대기열 → PC). ✅ 완성 표시는 P7 로 | `pa/server.py`, `dashboard/index.html`, `pa/mobile.py` | 버튼으로 제출 |
| P3 시간 정하기 | Canvas 항목에도 할 시간 고정 (`tasks.earliest/slot_end` 를 Canvas 확인이 덮어쓰지 않게), `POST /api/move`, ⋯ → "시간 정하기" | `pa/collect_canvas.py`, `pa/db.py`, `pa/server.py` | 강의를 원하는 시간에 → 기존 자동 열기·▶ 가 그 시각에 |
| P4 쉬운 예약 | 종류별 기본 동작 (3-2 표): 미리(초안·자료) / 시작(열기·재생) / 끝(수강 확인·남은 시간 다시) | `pa/autoopen.py`, `pa/jobs.py` | 시간만 정하면 다 함 |
| P5 시간표 화면 | 1·2·3 장 (범위 자동·겹침·손잡이 끌기·되돌리기) | `dashboard/index.html` | 주차별 시간표 |
| P6 고급 예약 | `schedules` 표 + "+ 예약 추가" 창 (AI 프롬프트 · 만들어 둔 기능 고르기 · 반복) + 엔진 실행기 | `pa/schedules.py`, `pa/db.py`, `pa/server.py`, 화면 | 아무 작업이나 시각 예약 |
| P7 자동 제출 | 과제마다 제출 방식 ①②③, 예약 끝에 제출 | `pa/submit.py`, `pa/autoopen.py` | 완성본 자동 제출 |
| P8 PC 전원 | ① 예약 깨우기("이때 켜져 있어" + 예약 5분 전) · 💤 휴대폰 절전 · ②-1 대기 PC 가 매직 패킷 대신 보내기 · ③ 주기적 깨기 | `pa/power.py`, `pa/mobile.py`, `config/power.example.yaml` | 3-5 |

## 5. 정해야 할 것

- ~~옮기기 켜는 방법~~ → **블록마다 작은 손잡이 ⠿** (2026-11-22 사용자가 정함)
- 예약 깨우기를 위해 '절전 해제 타이머 허용'을 충전 중 '사용'으로 바꿀지 (P8 때)

## 6. 나중에 이야기할 것 — 꼭 만들 것(4장)이 끝난 뒤 (사용자 2026-11-22)

### 6-1. 디자인·버튼 구조 (생각 못 했을 것)
- **블록 누르면 작은 창(팝오버)**: 큰 주 버튼 하나(▶ 강의 열기 / ✍ 초안 / 📤 제출) + [시간 바꾸기] + ⋯. 자세한 건 옆 패널.
  바꾸고 나면 창이 저절로 닫혀 계속 시간표를 본다 (Apple HIG 의 캘린더 예시). 경고는 이 창 말고 따로 알림으로 (놓치기 쉬움).
- **휴대폰은 아래에서 올라오는 시트**: 블록·빈 칸을 누르면 아래 시트, 아래로 밀면 닫힘 (Google Calendar Android). 오른쪽 아래 **+ 떠 있는 버튼** → 예약 시트.
- **마우스 올리면 미리보기 카드**: 시간표 칸이 좁아 잘린 제목·강의실·마감·이유를 클릭 없이 (화면이 흔들리지 않게 위에 띄움).
- **오른쪽 클릭 메뉴**: 완료 · 시간 바꾸기 · 예약 · 복제 · 제외 (블록마다 맞는 것만).
- **빈 칸을 끌어서 새 블록**: 쓱 그으면 그 시간으로 "무엇을?" 작은 창 → 할 일 고르기 or 고급 예약 (Uday 시간표 앱: "원하는 시간 쓱 선택, 완료").
- **할 일 서랍**: 옆에 아직 시간 안 정한 할 일 목록 → 시간표로 끌어 넣으면 예약 (Amie·Akiflow).
- **확대·축소**: Ctrl+휠 · 핀치 · [−][+] 버튼으로 1시간 높이 바꾸기, 보던 시각이 가운데 유지 (Fantastical·Cron·Prisma). 마지막 크기 기억.
- **넉넉 / 촘촘** 보기 (Google Calendar 2026-07).
- **보는 날 수**: 7 · 5 · 3 · 1일, 휴대폰 기본 3일 (Fantastical 은 4일로 맞춰 칸을 넓게).
- **과목 색 범례 = 필터**: 범례의 과목을 누르면 그 과목만 / 숨기기. 종류 필터 (수업·계획·예약·AI).
- **예약 아이콘 + 상태 점**: ▶ ✍ 📄 🤖 📤 + 대기(회색) · 진행(파랑) · 끝(초록) · 실패(빨강).
- **지금 선 옆에 "다음: 15:00 생화학 ▶ (12분 뒤)"** 칩.
- **요일 머리줄에 하루 합계**: 계획 시간 / 남은 여유 작은 막대 (하루 최대 시간 넘으면 빨강).
- **단축키**: t 오늘 · ←→ 주 · n 새 예약 · Alt+끌기 복제 (Cron) · Delete · Ctrl+Z 되돌리기 · ? 도움말.
- **빠른 입력에 동작까지**: `생화학 17강 >수 15-16시 ▶` / `보고서 >토 10시 ✍ 📤`.

### 6-2. 기능 (생각 못 했을 것)
- **남은 강의 시간 이어서**: 덜 들은 강의는 남은 분만큼 자동으로 다음 빈 시간에 (LearningX 진도)
- **빈틈(버퍼)**: 수업·예약 앞뒤 10분 비우기, 이동 시간 (Reclaim 의 buffer·travel time)
- **습관 블록**: "매일 1시간 복습"처럼 시간이 정해지지 않은 반복 — 빈 곳에 알아서, 바쁘면 옮겨감 (Reclaim Habits)
- **놓친 블록 다시 짜기 버튼**: 지난 블록 중 안 끝낸 걸 한 번에 다음 빈 시간으로 (Structured Replan, Akiflow)
- **하루 마무리**: 저녁에 "오늘 계획 vs 실제(⏱)" 비교 + 내일 확인 (Sunsama 저녁 정리)
- **간격 복습**: 강의를 들은 날 기준 1·3·7일 뒤 짧은 복습 블록 (시험 복습 규칙을 강의에도)
- **집중 타이머**: 블록 시작 때 뽀모도로(25/5) 같이 켜기 — 지금 ⏱ 기록과 이어짐
- **겹친 블록 중 '주'와 '곁'**: 강의(주) 틀어 두고 단순 작업(곁) — 재생은 하나만

### 6-3. 장기: 마우스·키보드 자동 조작 (사용자 2026-11-22 — **이번 작업이 모두 끝난 뒤 리마인드**)
- API 가 없는 일(학교 사이트의 버튼, 다른 프로그램)을 화면을 보고 마우스로. 느리고 비효율적이어도 할 수 있는 일이 늘어남.
- 후보: Claude 의 computer use (스크린샷 → 클릭), Windows UI Automation (지금 ▶ 재생 버튼이 이 방식, `pa/autoplay.py`), Playwright (브라우저 안).
- 지켜야 할 것: 출석·제출처럼 기록이 남는 동작은 확인 후, 하는 동안 화면에 "비서가 조작 중" 표시, Esc 로 멈춤.

## 출처

- 범위 자동 조절 요청: [Airtable](https://community.airtable.com/t5/product-ideas/collapse-non-working-hours-in-calendar-interface-calendar-view/m-p/156798), [ClickUp](https://feedback.clickup.com/feature-requests/p/adjustable-time-in-calendar-views), [GNOME](https://discourse.gnome.org/t/is-there-a-way-to-show-only-work-hours-in-calendar-view/22505), [BusyCal 근무 시간 접기](https://www.busymac.com/docs/faqs/day-week-view-missing-hours)
- 겹침: [BusyCal](https://www.busymac.com/docs/faqs/declutter-day-week-view), [Atlassian 요청](https://jira.atlassian.com/browse/CONFCLOUD-81282), [The Events Calendar](https://theeventscalendar.com/support/forums/topic/weekly-view-horrible-overlap-help/)
- 짧은 블록: [GNOME](https://gitlab.gnome.org/GNOME/gnome-calendar/issues/409), [FullCalendar eventShortHeight](https://fullcalendar.io/docs/eventShortHeight), [Ubuntu](https://bugs.launchpad.net/bugs/1279842)
- 끌기·맞춤·그림자: [CoreUI](https://coreui.io/scheduler/docs/features/drag-and-drop/), [MUI](https://mui.com/x/react-scheduler/drag-interactions), [DayPilot](https://doc.daypilot.org/calendar/snap-to-grid/), [GNOME 그림자](https://gitlab.gnome.org/GNOME/gnome-calendar/issues/248), [KDE 그림자](https://invent.kde.org/pim/merkuro/-/issues/114), [Ashby 손잡이](https://www.ashbyhq.com/product-updates/better-drag-drop-experience-on-calendar)
- 휴대폰 터치: [W3C pointer events](https://lists.w3.org/Archives/Public/public-pointer-events/2017JanMar/0088.html), [hello-pangea touch](https://github.com/hello-pangea/dnd/blob/HEAD/docs/sensors/touch.md), [FullCalendar longPressDelay](https://fullcalendar.io/docs/longPressDelay), [Syncfusion 버그](https://www.syncfusion.com/forums/198243)
- 자동 스크롤: [GSAP](https://gsap.com/docs/v3/Plugins/Draggable/autoScroll), [FullCalendar dragScroll](https://fullcalendar.io/docs/dragScroll), [hello-pangea](https://raw.githubusercontent.com/hello-pangea/dnd/HEAD//docs/guides/auto-scrolling.md)
- 되돌리기·겹침 경고: [dev.to 네 가지 예외](https://dev.to/johnbuilds/drag-and-drop-rescheduling-with-dnd-kit-the-four-edge-cases-that-were-the-actual-feature-3e98), [saasui](https://www.saasui.design/blog/saas-drag-and-drop-reordering-ux-patterns), [KDE 연속 끌기](https://invent.kde.org/pim/merkuro/-/issues/127), [GNOME 되돌리기](https://gitlab.gnome.org/GNOME/gnome-calendar/issues/62)
- 접근성: [W3C WCAG 2.5.7](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements), [Mobiscroll](https://mobiscroll.com/docs/vue/eventcalendar/accessibility)
- 색: [DayFlow 다크 모드](https://dayflow-js.github.io/calendar/docs/features/dark-mode), [Mozilla](https://bugzilla.mozilla.org/show_bug.cgi?id=1608344), [Discourse](https://meta.discourse.org/t/calendar-events-unreadable-in-dark-mode-if-the-category-has-a-dark-color/372315), [FullCalendar eventContrastColor](https://fullcalendar.io/docs/eventContrastColor.md)
- 자동 배치 앱: [Motion·Akiflow·Sunsama 비교](https://www.morgen.so/blog-posts/akiflow-vs-motion), [ClickUp 비교](https://clickup.com/blog/sunsama-vs-motion/)
- 좁은 화면: [Mobiscroll 3일](https://forum.mobiscroll.com/t/how-to-show-only-3-day-in-a-week-in-mobile-view/1111), [PTC](https://support.ptc.com/help/servicemaxcore/en/articles/fsa/week-view.html)
- 지금 선·고정 머리줄: [Google](https://workspaceupdates.googleblog.com/2007/06/google-calendar-adds-current-time-line.html?hl=en), [Prisma Calendar](https://real1tyy.github.io/Prisma-Calendar/configuration/calendar-ui)
- 디자인·버튼 (6-1): [Apple HIG 팝오버](https://developer.apple.com/design/human-interface-guidelines/popovers.md), [Syncfusion 빠른 창](https://react.syncfusion.com/react-ui/scheduler/quick-popup/), [GNOME 팝오버 논의](https://gitlab.gnome.org/GNOME/gnome-calendar/-/issues/1090), [미리보기 카드 PR](https://github.com/BuilderIO/agent-native/pull/2598), [Google Calendar 시트](https://9to5google.com/2019/05/08/google-calendar-bottom-sheet/), [Material 시트](https://m1.material.io/components/bottom-sheets.html), [ServiceNow FAB](https://horizon.servicenow.com/native-mobile/components/mobile-component-floating-action-button), [Fantastical](https://apps.apple.com/app/fantastical/id975937182), [Amie](https://amie.so/best/calendar-apps), [Cron 밀도·확대](https://cron.com/changelog/2021-03-01-grid-density-and-resizing), [Cron 복제](https://cron.com/changelog/2021-02-15-mini-month-navigator-and-cut-copy-paste-duplicate), [Prisma 확대](https://real1tyy.github.io/Prisma-Calendar/features/calendar/calendar-view), [Google 밀도](https://workspaceupdates.googleblog.com/2026/07/updated-options-to-better-view-google-Calendar-on-large-monitors.html), [Uday](https://apps.apple.com/us/app/uday-%EC%8B%9C%EA%B0%84%ED%91%9C-%ED%95%99%EC%A0%90%EA%B4%80%EB%A6%AC-to-do-%ED%80%B5%EB%A9%94%EB%AA%A8/id1491180192?l=ko)
- 전원 (3-5): [Remote Control](https://code.claude.com/docs/en/remote-control), [Modern Standby 깨우기](https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/modern-standby-wake-sources), [Wi-Fi WoL 한계](https://tech.yahoo.com/computing/articles/want-see-magic-trick-turn-155238408.html), [작업 스케줄러 깨우기](https://learn.microsoft.com/en-us/answers/questions/651690/windows-11-does-not-wake-computer-to-run-scheduled?page=2)
- 기능 (6-2): [Reclaim](https://help.reclaim.ai/en/articles/6210740-reclaim-s-features), [Structured](https://apps.apple.com/app/structured-daily-planner/id1499198946), [Amie 플래너 비교](https://amie.so/best/daily-planner-apps)
