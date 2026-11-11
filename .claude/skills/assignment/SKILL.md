---
name: assignment
description: Canvas 과제(보고서, 배움노트, 결과보고서 등)를 시작하거나 초안을 쓸 때 사용. "과제 하자", "보고서 써줘", "배움노트" 등.
---

1. `bin/pa list` 로 해당 과제의 키·마감을 확인한다.
   과제 설명이 더 필요하면 `pa.canvas.get("/courses/<id>/assignments/<id>")` 의 description 을 읽는다.
2. **`~/report/CLAUDE.md` 를 읽고** 그 글쓰기·파일명 규칙을 따른다.
3. 관련 자료는 `~/study_system/materials/<과목>/` 와 `~/study_system/notes/<과목>/` 에서 찾는다.
   사용자의 노트에 있는 사용자 자신의 표현과 생각을 우선 활용한다.
4. 초안은 `~/report/` 에 규칙에 맞는 파일명으로 저장한다.
5. 제출은 사용자가 직접 한다. Canvas 과제는 제출하면 다음 `bin/pa run --full` 때 자동 완료된다.
