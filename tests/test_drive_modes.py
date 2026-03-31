"""
tests/test_drive_modes.py – Unit tests for camera/drive_modes.py
"""

import time
import threading
import pytest
from unittest.mock import MagicMock, patch
from camera.drive_modes import AEBController, Intervalometer


def _make_mock_camera(ev=0.0, iso=100, shutter_us=10000):
    cam = MagicMock()
    cam.ev = ev
    cam.iso = iso
    cam.shutter_us = shutter_us
    cam.capture_image.side_effect = lambda name=None: MagicMock(__str__=lambda s: f"/tmp/{name or 'img'}.jpg", name=f"{name or 'img'}.jpg")
    return cam


class TestAEBController:
    def test_default_bracket_three_frames(self):
        cam = _make_mock_camera()
        cam.set_ev = MagicMock(side_effect=lambda ev: setattr(cam, "ev", ev))
        aeb = AEBController(cam)
        with patch("time.sleep"):  # skip delays
            paths = aeb.shoot()
        assert len(paths) == 3

    def test_custom_offsets(self):
        cam = _make_mock_camera()
        cam.set_ev = MagicMock(side_effect=lambda ev: setattr(cam, "ev", ev))
        aeb = AEBController(cam)
        with patch("time.sleep"):
            paths = aeb.shoot(ev_offsets=[-2.0, 0.0, 1.0, 2.0])
        assert len(paths) == 4

    def test_ev_restored_after_shoot(self):
        cam = _make_mock_camera(ev=0.5)
        original_ev = cam.ev
        cam.set_ev = MagicMock(side_effect=lambda ev: setattr(cam, "ev", ev))
        aeb = AEBController(cam)
        with patch("time.sleep"):
            aeb.shoot()
        # set_ev should be called with original_ev as the last call (restore)
        last_call_ev = cam.set_ev.call_args_list[-1][0][0]
        assert last_call_ev == pytest.approx(original_ev)


class TestIntervalometer:
    def test_start_stop(self):
        cam = _make_mock_camera()
        timer = Intervalometer(cam)
        timer.start(interval_s=0.01, total_frames=3)
        time.sleep(0.2)
        timer.stop()
        assert cam.capture_image.call_count >= 1

    def test_not_running_initially(self):
        cam = _make_mock_camera()
        timer = Intervalometer(cam)
        assert not timer.running

    def test_callback_called(self):
        cam = _make_mock_camera()
        captured = []
        timer = Intervalometer(cam, on_capture=lambda p, n: captured.append(n))
        timer.start(interval_s=0.01, total_frames=2)
        time.sleep(0.3)
        timer.stop()
        assert len(captured) >= 1

    def test_total_frames_stops_timer(self):
        cam = _make_mock_camera()
        timer = Intervalometer(cam)
        timer.start(interval_s=0.01, total_frames=2)
        time.sleep(0.3)
        assert not timer.running
        assert cam.capture_image.call_count == 2
