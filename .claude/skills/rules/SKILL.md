---
name: rules
description: 비서의 규칙(계획 요일·하루 최대 시간·알림·시험 복습·과목 폴더·자료 찾기 범위·연결 개수·제외 규칙)을 바꿀 때 사용. "공부 요일 바꿔줘", "하루 최대 시간", "알림 시간", "자료 범위", "최대 몇 개", "다운로드 며칠" 등.
---

규칙은 설정 파일에만 있고, 프로그램은 읽기만 한다. **규칙을 바꾸는 건 이 대화에서만** 한다.

1. 무엇을 바꾸려는지 확인하고, 고치기 전에 "지금 값 → 새 값, 그러면 달라지는 것"을 보여 주고 동의를 받는다.
2. 아래 파일을 고친 뒤 `bin/pa run` (계획·캘린더에 반영. 알림은 다음 동기화 때 모든 일정에 다시 적용됨).
3. 이 저장소의 파일을 바꿨으면 커밋하고 push 한다 (루트 CLAUDE.md 의 git 규칙).

| 바꾸고 싶은 것 | 파일 · 항목 |
|---|---|
| 공부하는 요일·순서, 하루 시작·끝, 하루 최대 시간, 휴식, 큰 일 나누기, 몇 주 앞까지 계획 | `config/timetable.yaml` → `planner` |
| 종류별 기본 예상 시간 (강의·퀴즈·과제·할 일) | `config/timetable.yaml` → `planner.minutes` (한 항목만이면 `bin/pa time <키> <분>`) |
| 시험 복습 (며칠 전, 몇 분) | `config/timetable.yaml` → `planner.exam_review` |
| 저녁 마무리 시각 | `config/timetable.yaml` → `planner.evening_review` |
| 알림 (계획 몇 분 전, 마감 하루·3시간·1시간 전) | `config/timetable.yaml` → `reminders` |
| 수업 시간표·학기 시작·끝, 온라인 수업 과목 | `config/timetable.yaml` → `classes`, `semester_*`, `online_classes` |
| Canvas 과목 ↔ 폴더 (materials·notes) | `config/courses.yaml` (루트 CLAUDE.md 의 과목 대응표도 함께) |
| 자료 찾기 범위·확장자·빼는 단어, 연결 최대 개수, 다운로드 며칠 | `config/materials.yaml` |
| 계속 제외할 과제 (이것만 / 같은 이름 앞으로도 / 예외 `!키`) | `inbox.md` → `## 제외` |
| 휴대폰 화면 (저장소·브랜치) | `config/mobile.yaml` · 비밀번호는 `.env` 의 `PA_MOBILE_PASSWORD` (출력하지 않음) |
| 퀴즈 복습 기준 (기록 며칠까지 유효 등) | 코드 `pa/quiz.py` 의 상수 — 바꾸기 전에 사용자에게 설명 |

- 프로그램이 정하지 못하고 멈춘 것(⚠️ 확인 필요, 짝 후보 여러 개, 과목을 모르는 다운로드 등)은 사용자에게 물어 정한다.
  같은 일이 되풀이될 것 같으면 규칙으로 만들지 물어본다 — 몰래 규칙을 만들지 않는다.
