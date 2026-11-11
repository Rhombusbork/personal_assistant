# 사용법

```bash
# 동기화
.venv/bin/python -m pa.sync_timetable      # 대면 수업 시간표 → '수업 시간표' 캘린더
.venv/bin/python -m pa.sync_canvas         # Canvas 과제 마감 → '과제' 캘린더

# 할 일 (Canvas 온라인 강의·퀴즈·과제, 제출한 것은 자동 제외)
.venv/bin/python -m pa.tasks               # 남은 항목 (마감 순, 맨 앞이 키)
.venv/bin/python -m pa.tasks ignore a475087    # 조장만 제출 등 → 영구 제외
.venv/bin/python -m pa.tasks ignored           # 제외 목록 / unignore 로 되돌리기
.venv/bin/python -m pa.tasks done m2890903     # 강의 수강 완료 표시
.venv/bin/python -m pa.tasks time m2890903 80  # 예상 소요 시간 조정(분)
.venv/bin/python -m pa.tasks add "제목" --due 2026-11-12 --min 60   # 직접 할 일 추가 (--due 없으면 기한 없는 할 일)

# 학습 계획 → '학습 계획' 캘린더 (실행할 때마다 앞으로의 계획을 다시 짬)
.venv/bin/python -m pa.plan --dry-run      # 미리보기
.venv/bin/python -m pa.plan

# 온라인 강의 열기
.venv/bin/python -m pa.lectures            # 이번 주차 항목
.venv/bin/python -m pa.lectures 생약 --open 1
```

계획 규칙은 `config/timetable.yaml` 의 `planner` 에서 조정한다.
- 마감이 가까운 순으로, 월·수·금·토 빈 시간에 먼저 배치하고 부족하면 일요일 사용
- 대면 수업·약속(Google Calendar 의 바쁨 시간)은 피함, 하루 최대 `max_minutes_per_day`
- 같은 과목의 퀴즈·과제는 그 과목 강의 뒤에 배치

AI 기능은 API 키 없이 Claude Code CLI(`claude -p`, 내 구독)를 사용한다 — `pa/ai.py`.
