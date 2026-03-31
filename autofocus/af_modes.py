"""
af_modes.py – Autofocus mode orchestration.

Implements:
  * AF-S  – Single-shot autofocus: run CDAF once, then lock.
  * AF-C  – Continuous autofocus: run CDAF in a background loop.
  * Focus area selection: single-point, zone, wide.
  * Manual focus override via keyboard delta or absolute motor position.
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum, auto
from typing import Callable, Dict, Optional, Tuple

from autofocus.cdaf import CDAFController, measure_sharpness
from autofocus.motor import Direction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Focus area / ROI
# ---------------------------------------------------------------------------

class FocusArea(Enum):
    SINGLE_POINT = auto()
    ZONE         = auto()
    WIDE         = auto()


def build_roi(
    area: FocusArea,
    frame_w: int,
    frame_h: int,
    cx: Optional[float] = None,
    cy: Optional[float] = None,
) -> Optional[Tuple[int, int, int, int]]:
    """
    Return an (x, y, w, h) ROI tuple for the given focus area.

    Parameters
    ----------
    area:
        Focus area mode.
    frame_w, frame_h:
        Frame dimensions in pixels.
    cx, cy:
        Normalised centre coordinates [0..1] for SINGLE_POINT / ZONE.
        Default: centre of frame.
    """
    if cx is None:
        cx = 0.5
    if cy is None:
        cy = 0.5

    if area == FocusArea.WIDE:
        return None   # use full frame

    if area == FocusArea.SINGLE_POINT:
        size_w = int(frame_w * 0.10)
        size_h = int(frame_h * 0.10)
    else:   # ZONE
        size_w = int(frame_w * 0.30)
        size_h = int(frame_h * 0.30)

    x = max(0, int(cx * frame_w - size_w // 2))
    y = max(0, int(cy * frame_h - size_h // 2))
    x = min(x, frame_w - size_w)
    y = min(y, frame_h - size_h)
    return (x, y, size_w, size_h)


# ---------------------------------------------------------------------------
# AF mode state machine
# ---------------------------------------------------------------------------

class AFMode(Enum):
    MANUAL    = auto()
    AF_S      = auto()
    AF_C      = auto()


class AFController:
    """
    Top-level autofocus controller that manages mode, area, and motor.

    Parameters
    ----------
    cdaf:
        CDAFController instance.
    motor:
        Motor driver instance.
    capture_fn:
        Zero-argument callable returning the latest camera frame.
    af_c_interval:
        Seconds between AF-C iterations.
    """

    def __init__(
        self,
        cdaf: CDAFController,
        motor,  # noqa: ANN001
        capture_fn: Callable[[], "np.ndarray"],  # type: ignore[name-defined]  # noqa: F821
        af_c_interval: float = 0.5,
    ) -> None:
        self._cdaf = cdaf
        self._motor = motor
        self._capture_fn = capture_fn
        self._af_c_interval = af_c_interval

        self.mode: AFMode = AFMode.MANUAL
        self.area: FocusArea = FocusArea.WIDE
        self.focus_point: Tuple[float, float] = (0.5, 0.5)  # normalised cx, cy
        self.frame_size: Tuple[int, int] = (640, 480)

        self._lock = threading.Lock()
        self._afc_thread: Optional[threading.Thread] = None
        self._afc_stop = threading.Event()
        self._locked: bool = False
        self._current_score: float = 0.0

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------

    def set_mode(self, mode: AFMode) -> None:
        if mode == self.mode:
            return
        if self.mode == AFMode.AF_C:
            self._stop_afc()
        self.mode = mode
        self._locked = False
        if mode == AFMode.AF_C:
            self._start_afc()
        logger.info("AF mode → %s", mode.name)

    # ------------------------------------------------------------------
    # Focus area
    # ------------------------------------------------------------------

    def set_area(self, area: FocusArea) -> None:
        self.area = area

    def set_focus_point(self, cx: float, cy: float) -> None:
        self.focus_point = (cx, cy)

    def _roi(self) -> Optional[Tuple[int, int, int, int]]:
        return build_roi(
            self.area, *self.frame_size,
            cx=self.focus_point[0], cy=self.focus_point[1],
        )

    # ------------------------------------------------------------------
    # AF-S
    # ------------------------------------------------------------------

    def trigger_afs(self) -> int:
        """Run a single CDAF cycle synchronously and lock focus."""
        with self._lock:
            pos = self._cdaf.run_once(self._capture_fn, roi=self._roi())
            self._locked = True
            self._current_score = self._cdaf.best_score
        logger.info("AF-S locked at position %d", pos)
        return pos

    # ------------------------------------------------------------------
    # AF-C
    # ------------------------------------------------------------------

    def _start_afc(self) -> None:
        self._afc_stop.clear()
        self._afc_thread = threading.Thread(
            target=self._afc_loop, daemon=True
        )
        self._afc_thread.start()

    def _stop_afc(self) -> None:
        self._afc_stop.set()
        if self._afc_thread:
            self._afc_thread.join(timeout=5)
        self._afc_thread = None

    def _afc_loop(self) -> None:
        while not self._afc_stop.is_set():
            with self._lock:
                try:
                    self._cdaf.run_once(self._capture_fn, roi=self._roi())
                    self._current_score = self._cdaf.best_score
                except Exception as exc:  # noqa: BLE001
                    logger.error("AF-C iteration error: %s", exc)
            self._afc_stop.wait(self._af_c_interval)

    # ------------------------------------------------------------------
    # Manual focus override
    # ------------------------------------------------------------------

    def manual_step(self, delta: int) -> None:
        """Move the lens by *delta* steps (positive = forward)."""
        direction = Direction.FORWARD if delta > 0 else Direction.BACKWARD
        with self._lock:
            self._motor.step(abs(delta), direction)
        logger.debug("Manual focus step %+d → pos=%d", delta, self._motor.position)

    def manual_goto(self, position: int) -> None:
        """Drive the motor to an absolute *position*."""
        with self._lock:
            current = self._motor.position
            delta = position - current
            if delta == 0:
                return
            d = Direction.FORWARD if delta > 0 else Direction.BACKWARD
            self._motor.step(abs(delta), d)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def is_locked(self) -> bool:
        return self._locked

    @property
    def current_score(self) -> float:
        return self._current_score

    @property
    def motor_position(self) -> int:
        return self._motor.position

    def stop(self) -> None:
        if self.mode == AFMode.AF_C:
            self._stop_afc()
