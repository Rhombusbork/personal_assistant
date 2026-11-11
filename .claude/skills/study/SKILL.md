---
name: study
description: 강의를 들으며 공부하거나, 강의 내용 질문·기록·정리를 할 때 사용. "공부하자", "이거 무슨 뜻이야", "기록해줘", "강의 열어줘" 등.
---

1. **`~/study_system/CLAUDE.md` 를 읽고** 그 진행 방식과 기록 원칙을 그대로 따른다
   (사용자의 말을 그대로 기록, 다듬지 않음 등).
2. 강의를 열어 달라고 하면 `bin/pa lectures <과목>` 으로 목록을 보여주고
   `--open N` 으로 연다.
3. 강의를 다 들었다고 하면 `bin/pa list` 에서 키를 찾아 `inbox.md` 의 `## 완료` 에 적고 `bin/pa run` 을 실행한다.
4. 과목명은 루트 CLAUDE.md 의 과목 대응표로 notes/materials 폴더를 찾는다.
