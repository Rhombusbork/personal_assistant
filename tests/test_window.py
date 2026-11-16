"""대시보드 창 지키기: 창이 reopen_minutes 동안 없으면 한 번 연다. 잠들었다 깬 직후·'오늘은 끄기'에는 열지 않는다."""
from pa import pipeline


def setup(monkeypatch, viewers, paused=False, minutes=3):
    clock = {"t": 1000.0}
    opened = []
    monkeypatch.setattr(pipeline.time, "time", lambda: clock["t"])
    monkeypatch.setattr(pipeline.server, "viewer_count", lambda window=45: viewers["n"])
    monkeypatch.setattr(pipeline, "reopen_minutes", lambda: minutes)
    monkeypatch.setattr(pipeline, "dash_paused", lambda: paused)
    monkeypatch.setattr(pipeline, "open_dashboard", lambda reason="": opened.append(clock["t"]))
    pipeline.WIN.update(missing_since=None, tick=clock["t"])
    return clock, opened


def run_for(clock, seconds, step=5):
    for _ in range(int(seconds // step)):
        clock["t"] += step
        pipeline._keep_window(True)


def test_reopens_after_minutes_without_window(monkeypatch):
    viewers = {"n": 1}
    clock, opened = setup(monkeypatch, viewers)
    run_for(clock, 600)
    assert opened == []                      # 창이 있는 동안은 안 엶
    viewers["n"] = 0
    run_for(clock, 170)
    assert opened == []                      # 3분 전에는 안 엶
    run_for(clock, 20)
    assert len(opened) == 1                  # 3분 지나면 한 번
    viewers["n"] = 1
    run_for(clock, 600)
    assert len(opened) == 1


def test_wake_from_sleep_and_pause(monkeypatch):
    viewers = {"n": 0}
    clock, opened = setup(monkeypatch, viewers)
    clock["t"] += 3600                       # 한 시간 잠들었다 깸
    pipeline._keep_window(True)
    run_for(clock, 120)
    assert opened == []                      # 깬 직후엔 기다린다
    clock, opened = setup(monkeypatch, viewers, paused=True)
    run_for(clock, 900)
    assert opened == []                      # 오늘은 끔
    clock, opened = setup(monkeypatch, viewers, minutes=0)
    run_for(clock, 900)
    assert opened == []                      # 설정 0 = 안 함
