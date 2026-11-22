"""PA_ENGINE=off 인 PC 에서는 엔진·계획 명령이 아무것도 하지 않고 끝난다."""
import sys

import pytest

from pa import __main__ as cli
from pa import pipeline


@pytest.mark.parametrize("cmd,code", [("watch", 0), ("run", 0), ("plan", 0), ("dashboard-check", 1)])
def test_engine_off_blocks(monkeypatch, capsys, cmd, code):
    monkeypatch.setenv("PA_ENGINE", "off")
    monkeypatch.setattr(sys, "argv", ["pa", cmd])
    monkeypatch.setattr(pipeline, "watch", lambda: pytest.fail("엔진이 켜짐"))
    monkeypatch.setattr(pipeline, "run", lambda **k: pytest.fail("run 이 돌았음"))
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == code
    assert "PA_ENGINE=off" in capsys.readouterr().out


def test_engine_on_by_default(monkeypatch):
    monkeypatch.delenv("PA_ENGINE", raising=False)
    monkeypatch.setattr(cli, "engine_off", lambda: False)
    called = []
    monkeypatch.setattr(pipeline, "watch", lambda: called.append(1))
    monkeypatch.setattr(sys, "argv", ["pa", "watch"])
    monkeypatch.setattr(cli.db, "connect", lambda: None)
    cli.main()
    assert called == [1]
