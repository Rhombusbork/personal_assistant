"""R5 예상 시간 보정 — ⏱ 로 잰 실제 시간으로 예상을 고친다 (계획 오류 대응).

끝난 할 일마다 (실제로 잰 시간 합) / (처음 예상) 비율을 구하고,
같은 종류·과목끼리 중앙값을 낸다. 3번 이상 쌓여야 쓴다.
  1순위: 종류+과목 (예: 유기약화학 강의)
  2순위: 종류      (예: 강의 전체)
"""
from statistics import median

from pa.model import short_course

MIN_SAMPLES = 3
LOW, HIGH = 0.5, 3.0


def samples(conn):
    rows = conn.execute("""
        SELECT t.key, t.kind, t.course, t.minutes AS est, SUM(s.minutes) AS actual
        FROM tasks t JOIN sessions s ON s.key = t.key
        WHERE t.status = 'done' AND s.minutes IS NOT NULL AND t.minutes > 0
        GROUP BY t.key""").fetchall()
    return [(r["kind"], short_course(r["course"]), r["actual"] / r["est"]) for r in rows if r["actual"]]


def factors(conn):
    """{(종류, 과목) 또는 (종류,): (배율, 표본 수)}"""
    groups = {}
    for kind, course, ratio in samples(conn):
        groups.setdefault((kind, course), []).append(ratio)
        groups.setdefault((kind,), []).append(ratio)
    return {k: (min(HIGH, max(LOW, median(v))), len(v)) for k, v in groups.items() if len(v) >= MIN_SAMPLES}


def factor_for(fs, kind, course):
    hit = fs.get((kind, short_course(course))) or fs.get((kind,))
    return hit[0] if hit else 1.0


def tracked(conn):
    """아직 안 끝난 할 일에 이미 쓴 시간 {키: 분}."""
    return {r["key"]: r["m"] for r in conn.execute(
        "SELECT s.key, SUM(s.minutes) AS m FROM sessions s JOIN tasks t ON t.key = s.key "
        "WHERE t.status = 'open' AND s.minutes IS NOT NULL GROUP BY s.key")}


def describe(conn):
    """대시보드용: [{'what': '강의 · 유기약화학', 'factor': 1.3, 'n': 5}]"""
    from pa.model import KIND_LABEL
    out = []
    for k, (f, n) in sorted(factors(conn).items(), key=lambda x: (len(x[0]), x[0])):
        what = KIND_LABEL.get(k[0], k[0]) + (f" · {k[1]}" if len(k) > 1 and k[1] else " 전체")
        out.append({"what": what, "factor": round(f, 2), "n": n})
    return out
