"""
tests/test_overlays.py – Unit tests for ui/overlays.py
"""

import numpy as np
import pytest
from ui.overlays import (
    apply_focus_peaking,
    digital_punchin,
    draw_center_cross,
    draw_diagonal_grid,
    draw_rule_of_thirds,
)


def _frame(h=64, w=64):
    rng = np.random.default_rng(0)
    return rng.integers(50, 200, (h, w, 3), dtype=np.uint8)


class TestCompositionOverlays:
    def test_rule_of_thirds_shape(self):
        f = _frame()
        out = draw_rule_of_thirds(f)
        assert out.shape == f.shape
        assert out.dtype == np.uint8

    def test_center_cross_shape(self):
        f = _frame()
        out = draw_center_cross(f)
        assert out.shape == f.shape

    def test_diagonal_grid_shape(self):
        f = _frame()
        out = draw_diagonal_grid(f)
        assert out.shape == f.shape

    def test_overlays_modify_frame(self):
        f = _frame()
        out = draw_rule_of_thirds(f)
        # Overlay should change at least some pixels
        assert not np.array_equal(f, out)


class TestFocusPeaking:
    def test_output_shape(self):
        f = _frame()
        out = apply_focus_peaking(f)
        assert out.shape == f.shape
        assert out.dtype == np.uint8

    def test_uniform_frame_unchanged(self):
        f = np.full((64, 64, 3), 128, dtype=np.uint8)
        out = apply_focus_peaking(f, threshold=0.1)
        # Uniform frame has no edges → output == input
        np.testing.assert_array_equal(f, out)

    def test_checkerboard_colourised(self):
        f = np.zeros((64, 64, 3), dtype=np.uint8)
        f[::2, ::2] = 200
        out = apply_focus_peaking(f, threshold=0.05)
        # Should differ from input due to colouring
        assert not np.array_equal(f, out)


class TestDigitalPunchin:
    def test_output_shape(self):
        f = _frame()
        out = digital_punchin(f)
        assert out.shape == f.shape

    def test_zoom_changes_content(self):
        f = _frame()
        out = digital_punchin(f, zoom=2.0)
        # Zoomed frame must differ from original
        assert not np.array_equal(f, out)

    def test_centre_point_respected(self):
        f = np.zeros((64, 64, 3), dtype=np.uint8)
        f[32, 32] = [255, 0, 0]
        # Punching in at centre should keep centre pixel red
        out = digital_punchin(f, cx=0.5, cy=0.5, zoom=2.0)
        assert out[32, 32, 0] == 255
