"""
tests/test_exposure.py – Unit tests for camera/exposure.py
"""

import pytest
from camera.exposure import (
    all_shutter_labels,
    ev_label,
    ev_steps,
    iso_label,
    shutter_label,
    shutter_to_us,
)


class TestShutterLabel:
    def test_fractions(self):
        assert shutter_label(4000) == "1/250"
        assert shutter_label(1_000_000) == '1"'
        assert shutter_label(500_000) == "1/2"

    def test_round_trip(self):
        for label in ("1/500", "1/250", "1/60", "1/30"):
            us = shutter_to_us(label)
            assert us > 0
            # reconstructed label may differ by rounding; just check it converts back
            assert shutter_to_us(shutter_label(us)) == us

    def test_whole_second(self):
        assert shutter_label(2_000_000) == '2"'

    def test_shutter_to_us_fraction(self):
        assert shutter_to_us("1/250") == 4000

    def test_shutter_to_us_seconds(self):
        assert shutter_to_us('2"') == 2_000_000


class TestAllShutterLabels:
    def test_returns_list(self):
        labels = all_shutter_labels()
        assert isinstance(labels, list)
        assert len(labels) > 10

    def test_contains_common_speeds(self):
        labels = all_shutter_labels()
        assert "1/250" in labels
        assert "1/60" in labels


class TestEV:
    def test_ev_steps_range(self):
        steps = ev_steps()
        assert steps[0] == pytest.approx(-3.0)
        assert steps[-1] == pytest.approx(3.0)

    def test_ev_steps_third_stops(self):
        steps = ev_steps()
        for i in range(len(steps) - 1):
            diff = round(steps[i + 1] - steps[i], 5)
            assert diff == pytest.approx(0.3, abs=1e-4)

    def test_ev_label_zero(self):
        assert ev_label(0.0) == "±0 EV"

    def test_ev_label_positive(self):
        assert ev_label(1.3) == "+1.3 EV"

    def test_ev_label_negative(self):
        assert ev_label(-0.7) == "-0.7 EV"


class TestISO:
    def test_iso_label(self):
        assert iso_label(400) == "ISO 400"
