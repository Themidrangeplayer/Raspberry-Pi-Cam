"""
histogram.py – Live histogram computation and canvas rendering.

Works purely with numpy arrays; tkinter drawing is done via the canvas
passed in, keeping this module testable without a display.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def compute_histogram(
    frame: np.ndarray,
    bins: int = 256,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute per-channel histograms for an HxWx3 RGB uint8 frame.

    Returns
    -------
    (r_hist, g_hist, b_hist)  each shape (bins,), dtype float32 normalised to 1.
    """
    def _chan(c: int) -> np.ndarray:
        hist, _ = np.histogram(frame[..., c].ravel(), bins=bins, range=(0, 256))
        h = hist.astype(np.float32)
        mx = h.max()
        return h / mx if mx > 0 else h

    return _chan(0), _chan(1), _chan(2)


# ---------------------------------------------------------------------------
# Tkinter canvas renderer
# ---------------------------------------------------------------------------

def draw_histogram(
    canvas,  # tk.Canvas
    frame: np.ndarray,
    *,
    width: int = 256,
    height: int = 80,
    bg: str = "#1a1a1a",
    alpha_blend: bool = True,
) -> None:
    """
    Render a live RGB histogram onto *canvas*.

    The canvas is cleared and redrawn each call.
    """
    canvas.delete("hist")

    # Background
    canvas.create_rectangle(
        0, 0, width, height,
        fill=bg, outline="", tags="hist",
    )

    r_hist, g_hist, b_hist = compute_histogram(frame)

    channel_config = [
        (r_hist, "#e05050"),
        (g_hist, "#50e050"),
        (b_hist, "#5080e0"),
    ]
    bin_w = width / len(r_hist)

    for hist, colour in channel_config:
        for i, val in enumerate(hist):
            bar_h = int(val * height)
            if bar_h == 0:
                continue
            x0 = i * bin_w
            x1 = x0 + bin_w
            y0 = height - bar_h
            canvas.create_rectangle(
                x0, y0, x1, height,
                fill=colour, outline="", stipple="gray50" if alpha_blend else "",
                tags="hist",
            )

    # Axes
    canvas.create_line(0, height - 1, width, height - 1, fill="#555555", tags="hist")
