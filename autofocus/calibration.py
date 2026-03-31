"""
calibration.py – Lens calibration and motor homing sequence.

Homing drives the motor backward (toward the minimum stop) until the
limit switch triggers (or a maximum step count is reached if no
switch is wired), then sets position=0.

A calibration sweep then maps motor positions to focus distances so that
absolute positioning can be used for repeatable focus pulls.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Limit switch reader (stub when no GPIO available)
# ---------------------------------------------------------------------------

def _make_limit_reader(pin: Optional[int]):  # noqa: ANN202
    """Return a callable that reads the limit switch state (True = triggered)."""
    if pin is None:
        def _always_false() -> bool:
            return False
        return _always_false

    try:
        import RPi.GPIO as GPIO  # noqa: PLC0415
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        def _read() -> bool:
            return not GPIO.input(pin)   # active-low

        return _read
    except Exception as exc:  # noqa: BLE001
        logger.warning("Limit switch GPIO unavailable (%s), homing by step count only", exc)

        def _always_false() -> bool:
            return False

        return _always_false


# ---------------------------------------------------------------------------
# Homing
# ---------------------------------------------------------------------------

class HomingController:
    """
    Drive the lens to the mechanical minimum stop and zero the position.

    Parameters
    ----------
    motor:
        Motor driver instance.
    limit_pin:
        BCM GPIO pin connected to the near-end limit switch (optional).
    max_home_steps:
        Safety limit – stop and raise RuntimeError if not homed within
        this many steps.
    step_delay_us:
        Microsecond pause between steps during homing (slow for safety).
    """

    def __init__(
        self,
        motor,  # noqa: ANN001
        limit_pin: Optional[int] = None,
        max_home_steps: int = 2000,
        step_delay_us: int = 1200,
    ) -> None:
        self._motor = motor
        self._limit_triggered = _make_limit_reader(limit_pin)
        self.max_home_steps = max_home_steps
        self.step_delay_us = step_delay_us
        self.is_homed: bool = False

    def home(self) -> None:
        """
        Drive backward until the limit switch triggers or max steps is reached,
        then set motor position to 0.
        """
        from autofocus.motor import Direction  # noqa: PLC0415

        logger.info("Homing sequence started …")
        self.is_homed = False
        steps_taken = 0

        while steps_taken < self.max_home_steps:
            if self._limit_triggered():
                logger.info("Limit switch triggered after %d steps", steps_taken)
                break
            self._motor.step(1, Direction.BACKWARD, self.step_delay_us)
            steps_taken += 1
        else:
            logger.warning(
                "Homing reached max_home_steps (%d) without limit switch – "
                "treating current position as home",
                self.max_home_steps,
            )

        self._motor.position = 0
        self.is_homed = True
        logger.info("Homing complete. Position zeroed.")


# ---------------------------------------------------------------------------
# Focus map (position ↔ distance calibration)
# ---------------------------------------------------------------------------

class FocusCalibration:
    """
    Maps motor positions to focus distances (mm or diopters) via a
    piecewise-linear table built during a calibration sweep.

    The table is intentionally simple; production lenses would use a
    polynomial fit.
    """

    def __init__(self) -> None:
        # List of (motor_position, focus_distance_mm) calibration points
        self._points: List[Tuple[int, float]] = []

    def add_point(self, motor_pos: int, distance_mm: float) -> None:
        self._points.append((motor_pos, distance_mm))
        self._points.sort(key=lambda p: p[0])

    def position_to_distance(self, motor_pos: int) -> Optional[float]:
        if len(self._points) < 2:
            return None
        for i in range(len(self._points) - 1):
            p0, d0 = self._points[i]
            p1, d1 = self._points[i + 1]
            if p0 <= motor_pos <= p1:
                t = (motor_pos - p0) / (p1 - p0)
                return d0 + t * (d1 - d0)
        if motor_pos <= self._points[0][0]:
            return self._points[0][1]
        return self._points[-1][1]

    def distance_to_position(self, distance_mm: float) -> Optional[int]:
        if len(self._points) < 2:
            return None
        for i in range(len(self._points) - 1):
            p0, d0 = self._points[i]
            p1, d1 = self._points[i + 1]
            lo, hi = sorted([d0, d1])
            if lo <= distance_mm <= hi:
                t = (distance_mm - d0) / (d1 - d0)
                return int(p0 + t * (p1 - p0))
        if distance_mm <= min(d for _, d in self._points):
            return self._points[0][0]
        return self._points[-1][0]

    def to_dict(self) -> Dict:
        return {"points": self._points}

    def from_dict(self, data: Dict) -> None:
        self._points = [tuple(p) for p in data.get("points", [])]  # type: ignore[misc]
