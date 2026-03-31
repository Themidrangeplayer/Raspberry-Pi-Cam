"""
drive_modes.py – Auto Exposure Bracketing (AEB) and Intervalometer.

Both modes operate as thin controllers that call back into a
CameraManager; they do not own a camera themselves.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auto Exposure Bracketing
# ---------------------------------------------------------------------------

class AEBController:
    """
    Capture a bracket of exposures around the current EV setting.

    Usage::

        aeb = AEBController(camera_manager)
        paths = aeb.shoot(ev_offsets=[-1.0, 0.0, +1.0])
    """

    def __init__(self, camera) -> None:  # noqa: ANN001
        self._cam = camera

    def shoot(
        self,
        ev_offsets: Optional[List[float]] = None,
        *,
        base_ev: Optional[float] = None,
    ) -> List[str]:
        """
        Capture one frame per EV offset.

        Parameters
        ----------
        ev_offsets:
            List of EV offsets relative to *base_ev*.  Defaults to
            [-1.0, 0.0, +1.0].
        base_ev:
            Base EV from which offsets are applied.  Defaults to the
            camera's current EV.

        Returns
        -------
        List of captured file paths (strings).
        """
        if ev_offsets is None:
            ev_offsets = [-1.0, 0.0, 1.0]
        if base_ev is None:
            base_ev = self._cam.ev

        saved_ev = self._cam.ev
        paths: List[str] = []
        try:
            for offset in ev_offsets:
                ev = round(base_ev + offset, 1)
                self._cam.set_ev(ev)
                time.sleep(0.25)   # allow AE to settle
                ts = time.strftime("%Y%m%d_%H%M%S")
                ev_tag = f"{'p' if ev >= 0 else 'm'}{abs(int(ev * 10)):02d}"
                path = self._cam.capture_image(name=f"AEB_{ts}_{ev_tag}")
                paths.append(str(path))
                logger.info("AEB frame: EV=%+.1f  →  %s", ev, path)
        finally:
            self._cam.set_ev(saved_ev)
        return paths


# ---------------------------------------------------------------------------
# Intervalometer
# ---------------------------------------------------------------------------

class Intervalometer:
    """
    Capture frames at a fixed interval for time-lapse photography.

    Usage::

        timer = Intervalometer(camera_manager, on_capture=my_callback)
        timer.start(interval_s=5, total_frames=60)
        ...
        timer.stop()
    """

    def __init__(
        self,
        camera,  # noqa: ANN001
        on_capture: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        self._cam = camera
        self._on_capture = on_capture
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.frame_count: int = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        interval_s: float = 5.0,
        total_frames: int = 0,
    ) -> None:
        """
        Begin time-lapse capture.

        Parameters
        ----------
        interval_s:
            Seconds between captures.
        total_frames:
            Stop after this many frames.  0 means run indefinitely.
        """
        if self.running:
            logger.warning("Intervalometer already running")
            return
        self._stop_event.clear()
        self.frame_count = 0
        self._thread = threading.Thread(
            target=self._run,
            args=(interval_s, total_frames),
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Intervalometer started: interval=%.1fs frames=%d",
            interval_s, total_frames,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Intervalometer stopped after %d frames", self.frame_count)

    def _run(self, interval_s: float, total_frames: int) -> None:
        while not self._stop_event.is_set():
            ts = time.strftime("%Y%m%d_%H%M%S")
            path = self._cam.capture_image(name=f"TL_{ts}_{self.frame_count:04d}")
            self.frame_count += 1
            if self._on_capture:
                try:
                    self._on_capture(str(path), self.frame_count)
                except Exception:  # noqa: BLE001
                    pass
            if total_frames and self.frame_count >= total_frames:
                break
            self._stop_event.wait(interval_s)
