"""
tests/test_cdaf.py – Unit tests for autofocus/cdaf.py
"""

import numpy as np
import pytest
from autofocus.cdaf import CDAFController, measure_sharpness
from autofocus.motor import _StubDriver, Direction


class TestMeasureSharpness:
    def test_uniform_frame_low_score(self):
        frame = np.full((64, 64, 3), 128, dtype=np.uint8)
        score = measure_sharpness(frame)
        assert score < 1.0

    def test_checkerboard_high_score(self):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        frame[::2, ::2] = 255
        score = measure_sharpness(frame)
        assert score > 100

    def test_roi_subset(self):
        frame = np.random.default_rng(7).integers(0, 256, (64, 64, 3), dtype=np.uint8)
        full_score = measure_sharpness(frame)
        roi_score = measure_sharpness(frame, roi=(10, 10, 20, 20))
        # Both should be positive; values may differ
        assert full_score >= 0
        assert roi_score >= 0

    def test_grey_input(self):
        grey = np.random.default_rng(3).integers(0, 256, (32, 32), dtype=np.uint8)
        score = measure_sharpness(grey)
        assert score >= 0

    def test_tiny_frame_returns_zero(self):
        frame = np.zeros((2, 2, 3), dtype=np.uint8)
        score = measure_sharpness(frame)
        assert score == 0.0


class TestCDAFController:
    def _make_cdaf(self, coarse=3, fine=2):
        motor = _StubDriver()
        cdaf = CDAFController(motor, coarse_steps=coarse, fine_steps=fine, step_delay_us=0)
        return cdaf, motor

    def test_run_once_returns_int(self):
        cdaf, _ = self._make_cdaf()
        frame = np.random.default_rng(1).integers(0, 256, (64, 64, 3), dtype=np.uint8)
        pos = cdaf.run_once(lambda: frame)
        assert isinstance(pos, int)

    def test_best_score_updated(self):
        cdaf, _ = self._make_cdaf()
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        frame[::2, ::2] = 255   # checkerboard
        cdaf.run_once(lambda: frame)
        assert cdaf.best_score > 0

    def test_best_position_set(self):
        cdaf, _ = self._make_cdaf()
        frame = np.random.default_rng(9).integers(0, 256, (64, 64, 3), dtype=np.uint8)
        cdaf.run_once(lambda: frame)
        assert cdaf.best_position is not None
