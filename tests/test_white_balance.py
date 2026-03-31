"""
tests/test_white_balance.py – Unit tests for camera/white_balance.py
"""

import pytest
from camera.white_balance import AWB_LABELS, AWB_MODES, KELVIN_MAX, KELVIN_MIN, kelvin_to_gains


class TestAWBModes:
    def test_labels_not_empty(self):
        assert len(AWB_LABELS) > 0

    def test_modes_match_labels(self):
        for label in AWB_LABELS:
            assert label in AWB_MODES

    def test_manual_in_labels(self):
        assert "Manual" in AWB_LABELS

    def test_auto_in_labels(self):
        assert "Auto" in AWB_LABELS


class TestKelvinGains:
    def test_returns_tuple(self):
        r, b = kelvin_to_gains(5500)
        assert isinstance(r, float)
        assert isinstance(b, float)

    def test_clamp_low(self):
        r, b = kelvin_to_gains(1000)   # below minimum
        r2, b2 = kelvin_to_gains(KELVIN_MIN)
        assert r == pytest.approx(r2)
        assert b == pytest.approx(b2)

    def test_clamp_high(self):
        r, b = kelvin_to_gains(20000)  # above maximum
        r2, b2 = kelvin_to_gains(KELVIN_MAX)
        assert r == pytest.approx(r2)
        assert b == pytest.approx(b2)

    def test_warm_has_high_r_low_b(self):
        r, b = kelvin_to_gains(2500)
        assert r > b

    def test_cool_has_low_r_high_b(self):
        r, b = kelvin_to_gains(7000)
        assert b > r

    def test_gains_positive(self):
        for k in range(KELVIN_MIN, KELVIN_MAX + 1, 500):
            r, b = kelvin_to_gains(k)
            assert r > 0
            assert b > 0
