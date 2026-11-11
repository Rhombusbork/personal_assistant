# 사용법

## 매일 쓰는 법 (Claude 없이)

1. VSCode 에서 `assistant.code-workspace` 를 연다 → **비서 감시기가 자동으로 켜진다**
   (처음 한 번 "자동 작업을 허용할까요?" 가 뜨면 허용)
2. **[TODAY.md](../TODAY.md)** 를 열고 `Ctrl+Shift+V` 로 미리보기 → 오늘 일정·마감·계획
3. 할 일 추가·완료·제외는 **[inbox.md](../inbox.md)** 에 적고 저장 → 몇 초 안에 계획·캘린더·TODAY.md 갱신
4. 대시보드: `dashboard/index.html` 을 오른쪽 클릭 → **Open with Live Server**

## inbox.md 문법

```markdown
## 할 일
- [ ] 리바이어던 발표자료 제출 @11-20 ~2h        마감 11/20 23:59, 예상 2시간
- [ ] 린스타트업 발표 @11-13 18:00 ~90m #창업     마감 시각, 과목
- [ ] 생화학 공부 ~1h 매주:화,목                  매주 그 요일 안에
- [ ] 논문 읽기                                    기한 없음 (장기 할 일)
- [x] 린스타트업 텍스트 제출 @11-11                체크 = 완료, 체크 풀면 다시 열림

## 완료
- m2890903                    키(TODAY.md 의 `...`)나 제목 단어 — 한 번 처리되면 지워도 완료 유지

## 제외
- 생약학 조별학습활동          여기 있는 동안 계속 제외 — 지우면 다시 나타남
```

- 반복 할 일 하나를 완료하려면 `## 완료` 에 날짜 붙은 키를 적는다: `i:생화학 공부@11-12`
- Canvas 과제·퀴즈는 **제출하면 자동으로 완료**된다 (조장 대표 제출 포함). 강의는 들은 뒤 `## 완료` 에 적는다.

## 명령 (`bin/pa`)

| 명령 | 하는 일 |
|---|---|
| `bin/pa watch` | 자동 감시 (VSCode 를 열면 자동 실행됨) |
| `bin/pa run [--full]` | 한 번 실행: inbox → (`--full` 이면 Canvas·과제 캘린더) → 계획 → TODAY.md·대시보드 |
| `bin/pa list` | 남은 할 일 (맨 앞이 키) |
| `bin/pa done/ignore/unignore <키>` | 완료 / 계속 제외 / 제외 취소 |
| `bin/pa time <키> <분>` | 예상 소요 시간 조정 |
| `bin/pa plan [--dry-run]` | 계획만 다시 |
| `bin/pa lectures [과목] [--open N]` | 이번 주 강의 목록·열기 |

VSCode 에서 `Ctrl+Shift+P → 작업 실행 → 비서: 지금 전체 동기화` 로도 실행할 수 있다.

## 계획 규칙 (`config/timetable.yaml` 의 `planner`)

- 마감이 가까운 순으로, 월·수·금·토 빈 시간에 먼저 배치하고 부족하면 일요일
- 대면 수업·약속(Google Calendar) 시간은 피함, 하루 최대 `max_minutes_per_day`
- 같은 과목의 퀴즈·과제는 그 과목 강의 뒤, 이미 시작한 블록은 고정

## 데이터

- `data/pa.db` (SQLite): `tasks` 할 일, `events` 자동 기록, `plan` 현재 계획, `busy` 수업·약속
- 모두 git 제외. 대시보드 데이터 `dashboard/data.js` 도 자동 생성·git 제외.
