"""mode=vscode: 바깥 창은 열지 않고, VSCode 가 켜져 있으면 확장에게 안 탭을 열라고 한다."""
from pa import pipeline, server


def test_vscode_mode_requests_tab_only_when_vscode_alive(monkeypatch):
    opened_app = []
    monkeypatch.setattr(pipeline, "dash_mode", lambda: "vscode")
    monkeypatch.setattr(pipeline.osutil, "open_app", lambda url: opened_app.append(url))
    server.OPEN_REQ.update(at=0, served=0)
    monkeypatch.setattr(server, "vscode_alive", lambda window=30: False)
    pipeline.open_dashboard("시험")
    assert server.OPEN_REQ["at"] == 0 and not opened_app          # VSCode 꺼짐 → 아무것도 안 함
    monkeypatch.setattr(server, "vscode_alive", lambda window=30: True)
    pipeline.open_dashboard("시험")
    assert server.OPEN_REQ["at"] > 0 and not opened_app           # 확장에게 요청, 바깥 창 없음
    first = server.OPEN_REQ["at"]
    server.OPEN_REQ["served"] = first + 1                           # 확장이 방금 가져감
    pipeline.open_dashboard("또")
    assert server.OPEN_REQ["at"] == first                           # 20초 안 두 번째 요청은 무시 (탭 중복 방지)

