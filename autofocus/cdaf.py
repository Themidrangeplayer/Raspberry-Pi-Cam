"""
cdaf.py – Contrast-Detection Autofocus algorithm.

The algorithm measures focus quality of a frame by computing a sharpness
metric over the selected region of interest (ROI), then drives the lens
motor through a hill-climbing search to maximise contrast.

Sharpness metric: normalised variance of the Laplacian, which is
hardware-independent and works on any greyscale or RGB image.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sharpness metric
# ---------------------------------------------------------------------------

def _laplacian_kernel() -> np.ndarray:
    return np.array([[0, -1, 0], [-1, 4, -1], [0, -1, 0]], dtype=np.float32)


def measure_sharpness(frame: np.ndarray, roi: Optional[Tuple[int, int, int, int]] = None) -> float:
    """
    Return a focus score for *frame* (higher = sharper).

    Parameters
    ----------
    frame:
        HxW or HxWx3 uint8 image.
    roi:
        Optional (x, y, w, h) crop in pixels.  If None, the whole frame
        is used.
    """
    if frame.ndim == 3:
        grey = (
            0.299 * frame[..., 0].astype(np.float32)
            + 0.587 * frame[..., 1].astype(np.float32)
            + 0.114 * frame[..., 2].astype(np.float32)
        )
    else:
        grey = frame.astype(np.float32)

    if roi is not None:
        x, y, w, h = roi
        grey = grey[y:y + h, x:x + w]

    # 2-D convolution with Laplacian kernel via sliding window sum
    # (avoids opencv dependency)
    k = _laplacian_kernel()
    from numpy.lib.stride_tricks import as_strided  # noqa: PLC0415

    gh, gw = grey.shape
    kh, kw = k.shape
    oh, ow = gh - kh + 1, gw - kw + 1
    if oh <= 0 or ow <= 0:
        return 0.0

    shape = (oh, ow, kh, kw)
    strides = grey.strides + grey.strides
    patches = as_strided(grey, shape=shape, strides=strides)
    lap = (patches * k).sum(axis=(-2, -1))
    return float(np.var(lap))


# ---------------------------------------------------------------------------
# Hill-climbing CDAF controller
# ---------------------------------------------------------------------------

class CDAFController:
    """
    Contrast-Detection Autofocus using a hill-climbing / ternary search.

    Parameters
    ----------
    motor:
        Motor driver instance (from ``autofocus.motor``).
    coarse_steps:
        Number of steps for the coarse sweep.
    fine_steps:
        Half-range for the fine refinement sweep.
    step_delay_us:
        Microsecond delay between motor steps.
    """

    def __init__(
        self,
        motor,  # noqa: ANN001
        coarse_steps: int = 10,
        fine_steps: int = 5,
        step_delay_us: int = 800,
    ) -> None:
        self._motor = motor
        self.coarse_steps = coarse_steps
        self.fine_steps = fine_steps
        self.step_delay_us = step_delay_us
        self._best_position: Optional[int] = None
        self._best_score: float = 0.0

    @property
    def best_position(self) -> Optional[int]:
        return self._best_position

    @property
    def best_score(self) -> float:
        return self._best_score

    def run_once(
        self,
        capture_fn,  # noqa: ANN001
        roi: Optional[Tuple[int, int, int, int]] = None,
    ) -> int:
        """
        Execute a single coarse+fine CDAF cycle.

        Parameters
        ----------
        capture_fn:
            Zero-argument callable that returns the latest frame (np.ndarray).
        roi:
            (x, y, w, h) region used for sharpness measurement.

        Returns
        -------
        Absolute motor position of best focus.
        """
        from autofocus.motor import Direction  # noqa: PLC0415

        start_pos = self._motor.position

        # ---- Coarse sweep (forward) ----
        scores: list[Tuple[int, float]] = []
        for _ in range(self.coarse_steps):
            self._motor.step(1, Direction.FORWARD, self.step_delay_us)
            frame = capture_fn()
            score = measure_sharpness(frame, roi)
            scores.append((self._motor.position, score))
            logger.debug("CDAF coarse pos=%d  score=%.2f", self._motor.position, score)

        best_pos, best_score = max(scores, key=lambda s: s[1])

        # Return to best coarse position
        current = self._motor.position
        delta = best_pos - current
        if delta != 0:
            d = Direction.FORWARD if delta > 0 else Direction.BACKWARD
            self._motor.step(abs(delta), d, self.step_delay_us)

        # ---- Fine sweep (±fine_steps around coarse best) ----
        fine_scores: list[Tuple[int, float]] = []
        self._motor.step(self.fine_steps, Direction.BACKWARD, self.step_delay_us)
        for _ in range(self.fine_steps * 2 + 1):
            self._motor.step(1, Direction.FORWARD, self.step_delay_us)
            frame = capture_fn()
            score = measure_sharpness(frame, roi)
            fine_scores.append((self._motor.position, score))
            logger.debug("CDAF fine   pos=%d  score=%.2f", self._motor.position, score)

        fine_best_pos, fine_best_score = max(fine_scores, key=lambda s: s[1])

        # Move to fine best
        current = self._motor.position
        delta = fine_best_pos - current
        if delta != 0:
            d = Direction.FORWARD if delta > 0 else Direction.BACKWARD
            self._motor.step(abs(delta), d, self.step_delay_us)

        self._best_position = self._motor.position
        self._best_score = fine_best_score
        logger.info(
            "CDAF complete: pos=%d  score=%.2f  (from %d)",
            self._best_position, self._best_score, start_pos,
        )
        return self._best_position
