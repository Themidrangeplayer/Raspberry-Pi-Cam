"""
tests/test_image_processing.py – Unit tests for camera/image_processing.py
"""

import numpy as np
import pytest
from camera.image_processing import (
    COLOUR_MATRIX_LABELS,
    COLOUR_MATRICES,
    IDENTITY_MATRIX,
    LUT,
    LUT_LABELS,
    LUTS,
    apply_colour_matrix,
    apply_lut,
)


def _make_frame(h=4, w=4, seed=42):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, (h, w, 3), dtype=np.uint8)


class TestColourMatrix:
    def test_identity_unchanged(self):
        frame = _make_frame()
        out = apply_colour_matrix(frame, IDENTITY_MATRIX)
        np.testing.assert_array_equal(frame, out)

    def test_output_shape_preserved(self):
        frame = _make_frame(8, 8)
        out = apply_colour_matrix(frame, COLOUR_MATRICES["Vivid"])
        assert out.shape == frame.shape

    def test_output_dtype(self):
        frame = _make_frame()
        out = apply_colour_matrix(frame, COLOUR_MATRICES["Cool"])
        assert out.dtype == np.uint8

    def test_values_clamped(self):
        frame = _make_frame()
        for name in COLOUR_MATRIX_LABELS:
            out = apply_colour_matrix(frame, COLOUR_MATRICES[name])
            assert out.min() >= 0
            assert out.max() <= 255

    def test_labels_list(self):
        assert "None" in COLOUR_MATRIX_LABELS
        assert "Vivid" in COLOUR_MATRIX_LABELS


class TestLUT:
    def test_identity_lut(self):
        lut = LUT.identity()
        frame = _make_frame()
        out = apply_lut(frame, lut)
        np.testing.assert_array_equal(frame, out)

    def test_s_curve_output_range(self):
        lut = LUT.s_curve()
        frame = _make_frame()
        out = apply_lut(frame, lut)
        assert out.min() >= 0
        assert out.max() <= 255

    def test_lut_shape(self):
        lut = LUT.identity()
        assert lut.table.shape == (256, 3)

    def test_catalogue_not_empty(self):
        assert len(LUTS) >= 2
        assert "None" in LUTS

    def test_lut_labels_match_dict(self):
        for label in LUT_LABELS:
            assert label in LUTS
