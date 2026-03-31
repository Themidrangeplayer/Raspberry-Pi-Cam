"""
overlays.py – Composition overlays, focus peaking, and digital punch-in.

All functions accept and return numpy uint8 RGB arrays so they are
independent of the display back-end and fully unit-testable.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Composition overlays
# ---------------------------------------------------------------------------

GRID_COLOR = (255, 255, 255)
GRID_ALPHA = 0.35


def draw_rule_of_thirds(frame: np.ndarray, alpha: float = GRID_ALPHA) -> np.ndarray:
    """Overlay a rule-of-thirds grid on *frame*."""
    out = frame.copy()
    h, w = out.shape[:2]
    overlay = frame.copy()

    for frac in (1 / 3, 2 / 3):
        x = int(w * frac)
        y = int(h * frac)
        overlay[:, x] = GRID_COLOR    # vertical
        overlay[y, :] = GRID_COLOR    # horizontal

    return _blend(frame, overlay, alpha)


def draw_center_cross(frame: np.ndarray, alpha: float = GRID_ALPHA) -> np.ndarray:
    """Overlay a centring cross."""
    out = frame.copy()
    h, w = out.shape[:2]
    overlay = frame.copy()
    cx, cy = w // 2, h // 2
    size = min(w, h) // 10
    overlay[cy, cx - size:cx + size] = GRID_COLOR
    overlay[cy - size:cy + size, cx] = GRID_COLOR
    return _blend(frame, overlay, alpha)


def draw_diagonal_grid(frame: np.ndarray, alpha: float = GRID_ALPHA) -> np.ndarray:
    """Draw diagonal (golden spiral) guide lines."""
    out = frame.copy()
    h, w = out.shape[:2]
    overlay = frame.copy()

    # Main diagonals
    for y in range(h):
        xf = int(y * w / h)
        xb = w - 1 - xf
        overlay[y, min(xf, w - 1)] = GRID_COLOR
        overlay[y, max(0, xb)] = GRID_COLOR

    return _blend(frame, overlay, alpha)


def _blend(base: np.ndarray, overlay: np.ndarray, alpha: float) -> np.ndarray:
    return np.clip(
        base.astype(np.float32) * (1 - alpha) + overlay.astype(np.float32) * alpha,
        0, 255,
    ).astype(np.uint8)


# ---------------------------------------------------------------------------
# Focus peaking
# ---------------------------------------------------------------------------

def apply_focus_peaking(
    frame: np.ndarray,
    threshold: float = 0.15,
    colour: Tuple[int, int, int] = (255, 50, 50),
) -> np.ndarray:
    """
    Highlight high-frequency (in-focus) areas in *colour*.

    A simple Laplacian edge strength mask is used as the focus indicator.
    Pixels whose normalised edge strength exceeds *threshold* are colourised.
    """
    grey = (
        0.299 * frame[..., 0].astype(np.float32)
        + 0.587 * frame[..., 1].astype(np.float32)
        + 0.114 * frame[..., 2].astype(np.float32)
    )

    # Laplacian via finite differences
    lap = np.abs(
        -4 * grey[1:-1, 1:-1]
        + grey[:-2, 1:-1]
        + grey[2:, 1:-1]
        + grey[1:-1, :-2]
        + grey[1:-1, 2:]
    )
    mx = lap.max()
    if mx == 0:
        return frame

    norm = lap / mx
    mask = norm > threshold   # True where edges are sharp

    out = frame.copy()
    for c, v in enumerate(colour):
        channel = out[1:-1, 1:-1, c].astype(np.float32)
        channel[mask] = channel[mask] * 0.4 + v * 0.6
        out[1:-1, 1:-1, c] = np.clip(channel, 0, 255).astype(np.uint8)

    return out


# ---------------------------------------------------------------------------
# Digital punch-in (magnified crop preview)
# ---------------------------------------------------------------------------

def digital_punchin(
    frame: np.ndarray,
    cx: float = 0.5,
    cy: float = 0.5,
    zoom: float = 3.0,
) -> np.ndarray:
    """
    Return a magnified crop centred at (*cx*, *cy*) (normalised coords).

    The result has the same resolution as the input frame.
    """
    h, w = frame.shape[:2]
    crop_w = max(1, int(w / zoom))
    crop_h = max(1, int(h / zoom))

    x0 = max(0, int(cx * w - crop_w // 2))
    y0 = max(0, int(cy * h - crop_h // 2))
    x0 = min(x0, w - crop_w)
    y0 = min(y0, h - crop_h)

    crop = frame[y0:y0 + crop_h, x0:x0 + crop_w]

    # Nearest-neighbour upscale to original size
    zoom_y = h / crop_h
    zoom_x = w / crop_w
    yi = (np.arange(h) / zoom_y).astype(int)
    xi = (np.arange(w) / zoom_x).astype(int)
    return crop[np.ix_(yi, xi)]
