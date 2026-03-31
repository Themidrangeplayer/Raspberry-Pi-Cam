"""
tests/test_histogram.py – Unit tests for ui/histogram.py
"""

import numpy as np
import pytest
from ui.histogram import compute_histogram


class TestComputeHistogram:
    def _frame(self, h=32, w=32):
        rng = np.random.default_rng(5)
        return rng.integers(0, 256, (h, w, 3), dtype=np.uint8)

    def test_returns_three_arrays(self):
        r, g, b = compute_histogram(self._frame())
        assert len(r) == 256
        assert len(g) == 256
        assert len(b) == 256

    def test_normalised_to_one(self):
        r, g, b = compute_histogram(self._frame())
        assert r.max() == pytest.approx(1.0)
        assert g.max() == pytest.approx(1.0)
        assert b.max() == pytest.approx(1.0)

    def test_all_same_value_single_peak(self):
        frame = np.full((16, 16, 3), 128, dtype=np.uint8)
        r, g, b = compute_histogram(frame)
        # All energy should be at bin 128
        assert r[128] == pytest.approx(1.0)
        assert r.sum() == pytest.approx(1.0)

    def test_custom_bins(self):
        r, g, b = compute_histogram(self._frame(), bins=64)
        assert len(r) == 64

    def test_all_values_non_negative(self):
        r, g, b = compute_histogram(self._frame())
        assert (r >= 0).all()
        assert (g >= 0).all()
        assert (b >= 0).all()
