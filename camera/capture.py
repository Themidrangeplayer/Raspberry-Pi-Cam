"""
capture.py – Central camera management.

Wraps picamera2 with a stub fallback so the application can run on a
development machine without Raspberry Pi hardware attached.
"""

from __future__ import annotations

import io
import logging
import time
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# picamera2 import with hardware stub fallback
# ---------------------------------------------------------------------------

try:
    from picamera2 import Picamera2
    from picamera2.controls import Controls
    PICAMERA2_AVAILABLE = True
except Exception:  # noqa: BLE001
    PICAMERA2_AVAILABLE = False
    logger.warning("picamera2 not available – running in stub mode")


class _StubCamera:
    """Minimal stand-in used on non-Pi hardware."""

    def __init__(self) -> None:
        self._running = False
        self._controls: dict = {}
        # Generate a test gradient frame once
        self._frame = self._make_test_frame()

    @staticmethod
    def _make_test_frame() -> np.ndarray:
        h, w = 480, 640
        img = np.zeros((h, w, 3), dtype=np.uint8)
        for y in range(h):
            for x in range(w):
                img[y, x] = [int(x * 255 / w), int(y * 255 / h), 128]
        return img

    # picamera2-compatible surface
    def configure(self, config) -> None:  # noqa: ANN001
        pass

    def create_preview_configuration(self, **kw):  # noqa: ANN201
        return {}

    def create_still_configuration(self, **kw):  # noqa: ANN201
        return {}

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def close(self) -> None:
        self._running = False

    def capture_array(self, name: str = "main") -> np.ndarray:
        return self._frame.copy()

    def capture_file(self, path: str, name: str = "main") -> None:
        try:
            from PIL import Image  # noqa: PLC0415
            img = Image.fromarray(self._frame)
            img.save(path)
        except Exception as exc:  # noqa: BLE001
            logger.error("Stub capture_file failed: %s", exc)

    def set_controls(self, controls: dict) -> None:
        self._controls.update(controls)

    def capture_metadata(self) -> dict:
        return {}


class CameraManager:
    """High-level camera interface used by the rest of the application."""

    # Sensor limits (used as defaults; real Pi camera may differ)
    SHUTTER_MIN_US = 100         # 1/10 000 s
    SHUTTER_MAX_US = 1_000_000   # 1 s
    ISO_VALUES = [100, 200, 400, 800, 1600, 3200]
    EV_RANGE = (-3.0, 3.0)

    def __init__(self, output_dir: str = "captures") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if PICAMERA2_AVAILABLE:
            self._cam: Picamera2 | _StubCamera = Picamera2()
        else:
            self._cam = _StubCamera()

        self._running = False
        self._current_controls: dict = {}

        # Defaults
        self.shutter_us: int = 10_000   # 1/100 s
        self.iso: int = 100
        self.ev: float = 0.0
        self.awb_mode: str = "auto"
        self.awb_gains: Optional[Tuple[float, float]] = None  # (r, b) for manual WB
        self.capture_raw: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_preview(self) -> None:
        """Configure the camera for live preview and start it."""
        if self._running:
            return
        config = self._cam.create_preview_configuration(
            main={"size": (640, 480), "format": "RGB888"},
        )
        self._cam.configure(config)
        self._cam.start()
        self._running = True
        self._apply_controls()
        logger.info("Camera preview started")

    def stop(self) -> None:
        if self._running:
            self._cam.stop()
            self._running = False

    def close(self) -> None:
        self.stop()
        self._cam.close()

    # ------------------------------------------------------------------
    # Frame capture
    # ------------------------------------------------------------------

    def capture_frame(self) -> np.ndarray:
        """Return the latest preview frame as an HxWx3 uint8 RGB array."""
        return self._cam.capture_array("main")

    def capture_image(self, name: Optional[str] = None) -> Path:
        """
        Capture a full-resolution still.

        Returns the path to the saved file.
        """
        ts = time.strftime("%Y%m%d_%H%M%S")
        stem = name or f"IMG_{ts}"

        if self.capture_raw and PICAMERA2_AVAILABLE:
            still_config = self._cam.create_still_configuration(
                raw={"size": self._cam.sensor_resolution},
                main={"size": (4056, 3040)},
            )
            self._cam.configure(still_config)
            dng_path = self.output_dir / f"{stem}.dng"
            jpg_path = self.output_dir / f"{stem}.jpg"
            self._cam.start()
            self._cam.capture_file(str(jpg_path), name="main")
            self._cam.capture_file(str(dng_path), name="raw")
            self.start_preview()
            return dng_path

        out_path = self.output_dir / f"{stem}.jpg"
        self._cam.capture_file(str(out_path))
        logger.info("Captured: %s", out_path)
        return out_path

    # ------------------------------------------------------------------
    # Exposure controls
    # ------------------------------------------------------------------

    def set_shutter_speed(self, microseconds: int) -> None:
        microseconds = max(self.SHUTTER_MIN_US, min(self.SHUTTER_MAX_US, microseconds))
        self.shutter_us = microseconds
        self._apply_controls()

    def set_iso(self, iso: int) -> None:
        if iso not in self.ISO_VALUES:
            iso = min(self.ISO_VALUES, key=lambda v: abs(v - iso))
        self.iso = iso
        self._apply_controls()

    def set_ev(self, ev: float) -> None:
        ev = max(self.EV_RANGE[0], min(self.EV_RANGE[1], ev))
        self.ev = ev
        self._apply_controls()

    # ------------------------------------------------------------------
    # White balance
    # ------------------------------------------------------------------

    def set_awb_mode(self, mode: str) -> None:
        """Set auto white balance mode ('auto', 'daylight', 'cloudy', etc.)."""
        self.awb_mode = mode
        self.awb_gains = None
        self._apply_controls()

    def set_manual_wb(self, r_gain: float, b_gain: float) -> None:
        self.awb_mode = "manual"
        self.awb_gains = (r_gain, b_gain)
        self._apply_controls()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_controls(self) -> dict:
        controls: dict = {
            "ExposureTime": self.shutter_us,
            "AnalogueGain": self.iso / 100.0,
            "ExposureValue": self.ev,
        }
        if self.awb_mode == "manual" and self.awb_gains:
            controls["AwbEnable"] = False
            controls["ColourGains"] = self.awb_gains
        else:
            controls["AwbEnable"] = True
        return controls

    def _apply_controls(self) -> None:
        if not self._running:
            return
        try:
            self._cam.set_controls(self._build_controls())
        except Exception as exc:  # noqa: BLE001
            logger.debug("set_controls skipped: %s", exc)
