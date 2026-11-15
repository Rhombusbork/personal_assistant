# 간결한 화면 설계 기법 정리 (대시보드 개편용)

> 2026-11-15 · 책·업계 자료 조사. 시안 3개(`dashboard/designs/`)는 이 기법들을 각각 다르게 조합한 것.
> 출처는 맨 아래. 2차 요약 자료가 섞여 있어 원문과 표현이 조금 다를 수 있다.

## 1. 원리 (책)

| 기법 | 출처 | 핵심 | 우리 화면에 쓰면 |
|---|---|---|---|
| **한 화면·한눈에** | Stephen Few, *Information Dashboard Design* | 대시보드는 "일에 필요한 가장 중요한 정보를 한 화면에, 한눈에 볼 수 있게". 실패 원인은 기술이 아니라 시각 설계. 중요한 것일수록 크게, 좋은 자리에 | 첫 화면(스크롤 없이)에 "지금 할 일·다음·마감"만 |
| **요약과 예외로 줄이기** | Few | 전부 보여 주지 말고 요약 + 이상한 것(예외)만 | 정상인 것은 숨기고 ⚠️ 와 D-1 만 드러내기 |
| **데이터-잉크 비율** | Tufte · Few | 정보가 아닌 잉크(테두리·배경·장식)를 줄인다 | 색 상자 배경·굵은 테두리 없애기 |
| **강조하려면 나머지를 죽인다** | Wathan·Schoger, *Refactoring UI* | 목표를 크게 하기보다 주변을 연하게·작게. 이름표는 작고 회색, 값은 진하게 | 메타 정보(과목·마감)는 회색 작은 글씨, 제목만 진하게 |
| **테두리는 마지막 수단** | *Refactoring UI* | 구분은 여백 → 배경 차이 → 그림자 → (마지막) 얇은 선 | 카드 테두리 대신 여백으로 묶기 |
| **간격 체계** | *Refactoring UI* · 8pt 그리드 | 정해진 간격 단계(4·8·16·24·32)만 쓴다. 여백을 넉넉히 시작해서 줄이기 | CSS 변수로 간격 고정 |
| **Hick의 법칙** | Yablonski, *Laws of UX* | 선택지가 많을수록 결정 시간이 늘어난다 (로그로) | 한 줄 버튼 7개 → 주 버튼 1 + ✓ + ⋯ |
| **Tesler의 법칙** | *Laws of UX* | 없앨 수 없는 복잡함은 '어디에 둘지'를 정한다 | 기능은 그대로, ⋯ 메뉴·시트·접기로 옮김 |
| **묶기 (Miller·Gestalt 근접)** | *Laws of UX* | 가까운 것은 한 무리로 읽힌다. 덩어리를 몇 개로 | "확인할 것" 하나로 경고·점수·공지·새 파일 묶기 |
| **점진적 공개** | Nielsen (NN/g, 2006) | 드물게 쓰는 기능은 두 번째 단계로. 깊이는 2~3단까지, "더 보기"는 눈에 띄게 | 통계·제외 목록·하고 싶은 일은 접어서 아래로 |

## 2. 업계 실제 사례

| 회사·제품 | 한 일 | 배울 점 |
|---|---|---|
| **Linear** (2024·2026 화면 개편, "더 차분하고 일관된 화면") | 사이드바를 몇 단계 어둡게, 아이콘 수·크기 줄이고 색 배경 아이콘 제거, 선을 부드럽게 해 "구조는 느껴지되 보이지 않게", 정보 밀도는 유지 | 작업 영역만 진하게, 탐색은 물러나게. 밀도는 지키고 소음만 줄이기 |
| **Things 3 / Apple 미리 알림** | "오늘" 하나에 집중, 큰 제목·여백, 체크 원 하나 | 한 줄 = 제목 + 체크. 나머지는 눌렀을 때 |
| **Google Calendar 일정 보기 · Sunsama** | 시간 순 목록, "지금" 선, 빈 시간 표시, 하루 계획 의식 | 타임라인이 첫 화면의 주인공 |
| **Material Design 3** | 그림자 대신 **톤(밝기 단계)으로 높이 표현**, 하단 시트로 세부 동작 | 색 상자 대신 회색 단계 2~3개, 줄을 누르면 시트에 모든 버튼 |
| **Superhuman · Linear** | 키보드 우선 + 명령 팔레트(Ctrl+K), 줄의 동작은 마우스를 올리거나 골랐을 때만 | 버튼을 늘 보여 주지 않아도 빠르게 |
| **받은편지함 정리 (Inbox Zero)** | 확인할 것을 한곳에 모아 하나씩 처리하고 비운다 | 경고·점수·공지·새 파일 → "확인할 것 N" 하나 |

## 3. 우리 대시보드 점검표 (개편 기준)

1. 스크롤 없이 첫 화면에 **지금 할 일 · 다음 · 3일 안 마감**이 보이는가 (Few)
2. 한 줄에 늘 보이는 버튼이 **2개 이하**인가 (Hick)
3. 색이 **의미가 있을 때만** 쓰였는가 — 종류 점·위험(D-1·지남)·강조 1색 (데이터-잉크)
4. 확인할 것이 **한곳**에 있는가, 다 처리하면 사라지는가 (묶기·Inbox Zero)
5. 드물게 쓰는 기능이 **2단계 안**에 있는가 (점진적 공개)
6. 테두리·배경 상자 대신 **여백·글자 크기·회색 단계**로 나눴는가 (*Refactoring UI*)
7. 휴대폰 폭(375px)에서 가로 스크롤 없이, 누르는 곳이 44px 이상인가
8. 없앤 기능이 없는가 — 옮겼을 뿐인가 (Tesler)

## 출처

- Progressive disclosure: [The Decision Lab](https://thedecisionlab.com/reference-guide/design/progressive-disclosure) · [UXPin](https://www.uxpin.com/studio/blog/what-is-progressive-disclosure/) · [IxDF](https://ixdf.org/encyclopedia/progressive_disclosure.html) · [Wikipedia](https://en.wikipedia.com/wiki/Progressive_disclosure) · [TNW 대시보드 가이드](https://thenextweb.com/news/a-designers-guide-to-creating-effective-dashboards) (NN/g 원문: nngroup.com/articles/progressive-disclosure)
- Linear: [Behind the latest design refresh](https://linear.app/now/behind-the-latest-design-refresh) · [2026-03 UI refresh](https://linear.app/changelog/2026-03-12-ui-refresh) · [How we redesigned the Linear UI](https://linear.app/now/how-we-redesigned-the-linear-ui) · [2024-03 new UI](https://linear.app/changelog/2024-03-20-new-linear-ui) · [Shortcut: calmer, clearer, faster](https://www.shortcut.com/blog/designing-a-calmer-clearer-faster-shortcut)
- Stephen Few: [UXmatters 서평](https://uxmatters.com/mt/archives/2007/04/book-review-information-dashboard-design.php) · [The Information Lab](https://www.theinformationlab.co.uk/community/blog/information-dashboard-design-stephen) · [Speckyboy](https://speckyboy.com/designing-information-dashboards/) · [ArcGIS 대시보드 작성 원칙](https://mercator.asu.edu/arcgis/help/en/portal/latest/use/author-effective-dashboards.htm)
- Refactoring UI (2차 요약): [DEV 서평](https://dev.to/updivision/book-review-refactoring-ui-by-adam-wathan-steve-schoger-2f7m) · [요약 노트](https://rjseymour66.github.io/webdev/refactoring-ui/)
- Material Design 3: [Tone-based surface color (Material 블로그)](https://material.io/blog/tone-based-surface-color-m3) · [Compose BottomSheet](https://developer.android.com/reference/kotlin/androidx/compose/material3/BottomSheet.composable)
- Laws of UX: [Hick's Law (lawsofux.com)](https://lawsofux.com/hicks-law/index.md) · [Adobe 소개](https://blog.adobe.com/en/publish/2018/04/17/ux-designers-need-check-laws-ux) · [Yext 적용 사례](https://medium.com/yext-design/yablonskis-laws-of-ux-and-how-we-use-them-2f6013fd7784)
