"""모든 테스트 공통: 진짜 학교 로그인·브라우저를 절대 쓰지 않는다 (.env 의 실제 계정으로 로그인한 일이 있었음)."""
import pytest


@pytest.fixture(autouse=True)
def _no_real_login(monkeypatch):
    from pa import browser
    monkeypatch.setattr(browser, "auto_login", lambda: False)
