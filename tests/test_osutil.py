"""운영체제별 처리 (pa/osutil.py): 잠금이 프로세스 사이에서 동작하는지, 환경마다 고르는 길이 맞는지."""
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from pa import materials, osutil

ROOT = Path(__file__).resolve().parent.parent


def test_kind_is_one_of_three():
    assert osutil.KIND in ("windows", "wsl", "linux")
    assert not (osutil.IS_WINDOWS and osutil.IS_WSL)


def _try_lock_elsewhere(path):
    """다른 프로세스에서 기다리지 않고 잠금을 잡아 본다 → 'True' / 'False'."""
    code = textwrap.dedent(f"""
        from pa import osutil
        with open({str(path)!r}, "a", encoding="utf-8") as f:
            print(osutil.lock(f, wait=False))
    """)
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8").stdout.strip()


def test_lock_blocks_other_process_until_closed(tmp_path):
    path = tmp_path / "x.lock"
    with open(path, "a", encoding="utf-8") as f:
        assert osutil.lock(f, wait=False)
        assert _try_lock_elsewhere(path) == "False"
    assert _try_lock_elsewhere(path) == "True"  # 닫으면 풀림


def test_downloads_dir_outside_wsl_is_home_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(osutil, "IS_WSL", False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert osutil.downloads_dir() is None  # 없으면 None
    (tmp_path / "Downloads").mkdir()
    assert osutil.downloads_dir() == tmp_path / "Downloads"


@pytest.mark.parametrize("kind", ["wsl", "windows", "linux"])
def test_open_url_picks_the_right_way(kind, monkeypatch):
    calls = []
    monkeypatch.setattr(osutil, "IS_WSL", kind == "wsl")
    monkeypatch.setattr(osutil, "IS_WINDOWS", kind == "windows")
    monkeypatch.setattr(osutil, "_spawn", lambda cmd: calls.append(("spawn", cmd)))
    monkeypatch.setattr(osutil.os, "startfile", lambda u: calls.append(("startfile", u)), raising=False)
    monkeypatch.setattr(osutil.webbrowser, "open", lambda u: calls.append(("browser", u)))
    osutil.open_url("https://example.com")
    assert calls == [{"wsl": ("spawn", ["explorer.exe", "https://example.com"]),
                      "windows": ("startfile", "https://example.com"),
                      "linux": ("browser", "https://example.com")}[kind]]


def test_pa_command_uses_this_python():
    assert osutil.pa_command("browser", "login") == [sys.executable, "-m", "pa", "browser", "login"]


def test_reveal_never_raises(monkeypatch, tmp_path):
    def boom(_):
        raise OSError("탐색기 없음")
    monkeypatch.setattr(osutil, "reveal", boom)
    assert materials.reveal(tmp_path / "a.md") is False
