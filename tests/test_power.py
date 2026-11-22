"""PC 전원 도구: 계산만 시험 (진짜 절전·작업 스케줄러는 건드리지 않음)."""
import pytest

from pa import power


def test_broadcast():
    assert power.broadcast("192.168.0.23", 24) == "192.168.0.255"
    assert power.broadcast("10.1.2.3", 16) == "10.1.255.255"


def test_wol_rejects_bad_mac():
    with pytest.raises(SystemExit):
        power.wol("12-34")
