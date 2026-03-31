"""
image_processing.py – RAW capture toggle, colour matrices, and LUT application.

All operations work on numpy uint8 HxWx3 arrays so they are independent
of the camera back-end and can be unit-tested without hardware.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colour Matrix
# ---------------------------------------------------------------------------

# A 3×3 colour-correction matrix applied as:  out = M @ [R, G, B]ᵀ  (clamped)
ColourMatrix = np.ndarray   # shape (3,3), dtype float32

IDENTITY_MATRIX: ColourMatrix = np.eye(3, dtype=np.float32)

VIVID_MATRIX: ColourMatrix = np.array([
    [1.4, -0.2, -0.2],
    [-0.1,  1.3, -0.1],
    [-0.1, -0.1,  1.4],
], dtype=np.float32)

COOL_MATRIX: ColourMatrix = np.array([
    [0.9,  0.05, 0.05],
    [0.0,  1.0,  0.05],
    [0.05, 0.05, 1.3],
], dtype=np.float32)

WARM_MATRIX: ColourMatrix = np.array([
    [1.3,  0.05, 0.0],
    [0.05, 1.0,  0.0],
    [0.0,  0.05, 0.9],
], dtype=np.float32)

COLOUR_MATRICES: Dict[str, ColourMatrix] = {
    "None":   IDENTITY_MATRIX,
    "Vivid":  VIVID_MATRIX,
    "Cool":   COOL_MATRIX,
    "Warm":   WARM_MATRIX,
}

COLOUR_MATRIX_LABELS: List[str] = list(COLOUR_MATRICES.keys())


def apply_colour_matrix(frame: np.ndarray, matrix: ColourMatrix) -> np.ndarray:
    """Apply a 3×3 colour matrix to an HxWx3 uint8 image."""
    if np.array_equal(matrix, IDENTITY_MATRIX):
        return frame
    f = frame.astype(np.float32) / 255.0
    out = np.einsum("ij,...j->...i", matrix, f)
    np.clip(out, 0.0, 1.0, out=out)
    return (out * 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# LUT (Look-Up Table)
# ---------------------------------------------------------------------------

class LUT:
    """1-D per-channel LUT, length 256."""

    def __init__(self, table: np.ndarray, name: str = "Custom") -> None:
        assert table.shape == (256, 3), "LUT must be shape (256, 3)"
        self.table = table.astype(np.uint8)
        self.name = name

    def apply(self, frame: np.ndarray) -> np.ndarray:
        out = np.empty_like(frame)
        for c in range(3):
            out[..., c] = self.table[frame[..., c], c]
        return out

    @classmethod
    def identity(cls) -> "LUT":
        t = np.tile(np.arange(256, dtype=np.uint8)[:, None], (1, 3))
        return cls(t, name="Identity")

    @classmethod
    def s_curve(cls, strength: float = 0.5) -> "LUT":
        """Simple S-curve contrast enhancement."""
        x = np.linspace(0.0, 1.0, 256)
        # Sigmoid-like: smoothstep centred on 0.5
        y = x + strength * (x * (1 - x) * (2 * x - 1))
        y = np.clip(y, 0.0, 1.0)
        t = np.tile((y * 255).astype(np.uint8)[:, None], (1, 3))
        return cls(t, name="S-Curve")


# Preset LUT catalogue
LUTS: Dict[str, LUT] = {
    "None":    LUT.identity(),
    "S-Curve": LUT.s_curve(0.5),
}

LUT_LABELS: List[str] = list(LUTS.keys())


def apply_lut(frame: np.ndarray, lut: LUT) -> np.ndarray:
    return lut.apply(frame)


def load_lut_from_file(path: str) -> Optional[LUT]:
    """
    Load a .cube or .npy LUT file.

    Only 1-D (per-channel) LUTs are supported; 3-D .cube files are skipped.
    Returns None if the file cannot be parsed.
    """
    p = Path(path)
    if p.suffix == ".npy":
        try:
            arr = np.load(str(p))
            return LUT(arr, name=p.stem)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load .npy LUT: %s", exc)
            return None
    logger.warning("Unsupported LUT format: %s", p.suffix)
    return None
