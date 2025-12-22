# tests/unit/simulation/test_roi.py
from celine.dt.apps.battery_sizing.roi import simple_payback, npv


def test_simple_payback():
    assert simple_payback(1000, 100) == 10
    assert simple_payback(1000, 0) is None


def test_npv_positive():
    assert npv(1000, 300, 0.05, 5) > 0
