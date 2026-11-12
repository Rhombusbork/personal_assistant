# Personal Assistant

개인 최적화 비서 프로그램.

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
- 다음: Windows 작업 스케줄러로 VSCode 없이도 실행, GitHub Pages 로 휴대폰에서 보기 (계획만)
- 종합 설계(욕구 분석·제안 기능·가능/불가능·로드맵): [docs/assistant-master-design.md](docs/assistant-master-design.md)

## 진행 상황

- [x] 1단계: 일정/할 일 관리 (시간표·Canvas 과제·학습 계획 → Google Calendar)
- [~] 2단계: 에이전틱 자동화된 할 일 수행 — 자료 자동 다운로드·수강 확인·보고서 초안·자료 요약·공지 정리·퀴즈 복습 (R1~R8, R10, R11 완료)
- [ ] 3단계: 컨디션/스트레스 관리 (보류)
