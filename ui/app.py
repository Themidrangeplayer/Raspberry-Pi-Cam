"""
app.py – Main tkinter application for the Raspberry Pi Camera.

Layout
------
┌──────────────────────────────────────────────────┬─────────────────┐
│                   Live Preview                   │ ┌─────────────┐ │
│                   (640 × 480)                    │ │  Tabs:      │ │
├──────────────────────────────────────────────────┤ │  Capture    │ │
│  Histogram                                       │ │  Exposure   │ │
├──────────────────────────────────────────────────┤ │  White Bal. │ │
│  Status bar                                      │ │  Processing │ │
└──────────────────────────────────────────────────┘ │  Aids       │ │
                                                   │  Drive      │ │
                                                   │  AF         │ │
                                                   └─────────────┘ │
                                                   └─────────────────┘
"""

from __future__ import annotations

import logging
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import numpy as np

from camera.capture import CameraManager
from camera.drive_modes import AEBController, Intervalometer
from camera.exposure import (
    ISO_VALUES,
    all_shutter_labels,
    ev_label,
    iso_label,
    shutter_label,
    shutter_to_us,
)
from camera.image_processing import COLOUR_MATRIX_LABELS, COLOUR_MATRICES, LUT_LABELS, LUTS
from camera.white_balance import AWB_LABELS, AWB_MODES, KELVIN_MAX, KELVIN_MIN, kelvin_to_gains
from autofocus.af_modes import AFController, AFMode, FocusArea
from autofocus.calibration import FocusCalibration, HomingController
from autofocus.cdaf import CDAFController
from autofocus.motor import create_driver
from ui.histogram import draw_histogram
from ui.overlays import (
    apply_focus_peaking,
    digital_punchin,
    draw_center_cross,
    draw_diagonal_grid,
    draw_rule_of_thirds,
)
from ui.widgets import (
    BG, BG_PANEL, BORDER, FG, FG_DIM, FONT_LABEL, FONT_SMALL, FONT_TITLE,
    FONT_VALUE, ACCENT,
    CycleButton, LabeledSlider, SectionHeader, SettingRow, configure_styles,
)

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("Pillow not installed – preview will show placeholder text")


PREVIEW_W = 640
PREVIEW_H = 480
PANEL_W   = 280
HIST_H    = 80


class CameraApp(tk.Tk):
    """Top-level application window."""

    def __init__(self, driver_type: str = "stub") -> None:
        super().__init__()
        self.title("Raspberry Pi Camera")
        self.configure(bg=BG)
        self.resizable(False, False)
        configure_styles()

        # ---- Camera & AF subsystems ----
        self._cam = CameraManager()
        self._motor = create_driver(driver_type)
        self._cdaf = CDAFController(self._motor)
        self._homing = HomingController(self._motor)
        self._focus_cal = FocusCalibration()
        self._af = AFController(
            self._cdaf, self._motor,
            capture_fn=self._cam.capture_frame,
        )
        self._aeb = AEBController(self._cam)
        self._timer = Intervalometer(self._cam, on_capture=self._on_timelapse_frame)

        # Overlay state
        self._overlay_mode: Optional[str] = None
        self._focus_peaking_on: bool = False
        self._punchin_on: bool = False
        self._focus_roi_cx: float = 0.5
        self._focus_roi_cy: float = 0.5

        # ---- Build UI ----
        self._build_layout()
        self._bind_keys()

        # ---- Start camera & preview loop ----
        self._cam.start_preview()
        self._preview_running = True
        self._update_preview()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        logger.info("CameraApp started")

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        # Main container
        main = ttk.Frame(self, style="TFrame")
        main.pack(fill="both", expand=True)

        # Left: preview + histogram + status
        left = ttk.Frame(main, style="TFrame")
        left.pack(side="left", fill="both")

        self._preview_canvas = tk.Canvas(
            left, width=PREVIEW_W, height=PREVIEW_H,
            bg="#000000", highlightthickness=0,
        )
        self._preview_canvas.pack()
        self._preview_canvas.bind("<Button-1>", self._on_preview_click)

        # Histogram canvas
        self._hist_canvas = tk.Canvas(
            left, width=PREVIEW_W, height=HIST_H,
            bg="#1a1a1a", highlightthickness=0,
        )
        self._hist_canvas.pack(fill="x")

        # Status bar
        self._status_var = tk.StringVar(value="Ready")
        status = tk.Label(
            left, textvariable=self._status_var,
            bg=BG, fg=FG_DIM, font=FONT_SMALL, anchor="w", padx=8,
        )
        status.pack(fill="x", pady=(2, 0))

        # Right: tabbed control panel
        panel_outer = tk.Frame(main, bg=BG_PANEL, width=PANEL_W)
        panel_outer.pack(side="right", fill="y")
        panel_outer.pack_propagate(False)

        self._notebook = ttk.Notebook(panel_outer)
        self._notebook.pack(fill="both", expand=True)

        self._build_tab_capture()
        self._build_tab_exposure()
        self._build_tab_white_balance()
        self._build_tab_processing()
        self._build_tab_aids()
        self._build_tab_drive()
        self._build_tab_af()

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _make_tab(self, title: str) -> ttk.Frame:
        """Create a new notebook tab and return its inner frame."""
        tab = ttk.Frame(self._notebook, style="Panel.TFrame", padding=4)
        self._notebook.add(tab, text=title)
        return tab

    def _build_tab_capture(self) -> None:
        p = self._make_tab("Capture")

        ttk.Button(
            p, text="⏺  CAPTURE", style="Accent.TButton",
            command=self._capture,
        ).pack(fill="x", pady=(4, 6))

        SectionHeader(p, "RAW Settings").pack(fill="x", pady=(8, 0))
        ttk.Label(p, text="RAW Capture", style="Panel.TLabel").pack(anchor="w", padx=4)
        self._raw_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            p, text="Enable DNG", variable=self._raw_var,
            command=lambda: setattr(self._cam, "capture_raw", self._raw_var.get()),
        ).pack(anchor="w", padx=8)

    def _build_tab_exposure(self) -> None:
        p = self._make_tab("Exposure")

        SectionHeader(p, "Exposure").pack(fill="x", pady=(4, 0))

        shutter_labels = all_shutter_labels()
        self._shutter_row = SettingRow(p, "Shutter", shutter_label(self._cam.shutter_us))
        self._shutter_row.pack(fill="x")
        shutter_ctrl = ttk.Combobox(
            p, values=shutter_labels, state="readonly", width=14,
            font=FONT_SMALL,
        )
        shutter_ctrl.set(shutter_label(self._cam.shutter_us))
        shutter_ctrl.pack(fill="x", padx=4)
        shutter_ctrl.bind("<<ComboboxSelected>>", self._on_shutter_change)
        self._shutter_combo = shutter_ctrl

        iso_labels = [iso_label(v) for v in ISO_VALUES]
        self._iso_row = SettingRow(p, "ISO", iso_label(self._cam.iso))
        self._iso_row.pack(fill="x")
        iso_ctrl = ttk.Combobox(p, values=iso_labels, state="readonly", width=14, font=FONT_SMALL)
        iso_ctrl.set(iso_label(self._cam.iso))
        iso_ctrl.pack(fill="x", padx=4)
        iso_ctrl.bind("<<ComboboxSelected>>", self._on_iso_change)

        self._ev_slider = LabeledSlider(
            p, "EV Comp.", from_=-3.0, to=3.0, initial=self._cam.ev,
            resolution=0.3, fmt="{:+.1f}",
            on_change=self._on_ev_change,
        )
        self._ev_slider.pack(fill="x")

    def _build_tab_white_balance(self) -> None:
        p = self._make_tab("White Bal.")

        SectionHeader(p, "White Balance").pack(fill="x", pady=(4, 0))

        wb_ctrl = ttk.Combobox(p, values=AWB_LABELS, state="readonly", width=14, font=FONT_SMALL)
        wb_ctrl.set("Auto")
        wb_ctrl.pack(fill="x", padx=4)
        wb_ctrl.bind("<<ComboboxSelected>>", self._on_wb_mode_change)
        self._wb_combo = wb_ctrl

        self._kelvin_slider = LabeledSlider(
            p, "Kelvin", from_=KELVIN_MIN, to=KELVIN_MAX,
            initial=5500, fmt="{:.0f} K",
            on_change=self._on_kelvin_change,
        )
        self._kelvin_slider.pack(fill="x")
        ttk.Label(
            p, text="(Active only in Manual WB mode)",
            style="Dim.TLabel",
        ).pack(anchor="w", padx=8)

    def _build_tab_processing(self) -> None:
        p = self._make_tab("Processing")

        SectionHeader(p, "Image Processing").pack(fill="x", pady=(4, 0))

        ttk.Label(p, text="Colour Matrix", style="Panel.TLabel").pack(anchor="w", padx=4)
        self._matrix_combo = ttk.Combobox(
            p, values=COLOUR_MATRIX_LABELS, state="readonly", width=14, font=FONT_SMALL,
        )
        self._matrix_combo.set("None")
        self._matrix_combo.pack(fill="x", padx=4)
        self._matrix_combo.bind("<<ComboboxSelected>>", self._on_matrix_change)
        self._active_matrix = None

        ttk.Label(p, text="LUT", style="Panel.TLabel").pack(anchor="w", padx=4)
        self._lut_combo = ttk.Combobox(
            p, values=LUT_LABELS, state="readonly", width=14, font=FONT_SMALL,
        )
        self._lut_combo.set("None")
        self._lut_combo.pack(fill="x", padx=4)
        self._lut_combo.bind("<<ComboboxSelected>>", self._on_lut_change)
        self._active_lut = None

    def _build_tab_aids(self) -> None:
        p = self._make_tab("Aids")

        SectionHeader(p, "Overlays").pack(fill="x", pady=(4, 0))
        overlays_frame = ttk.Frame(p, style="Panel.TFrame")
        overlays_frame.pack(fill="x", padx=4)
        self._overlay_var = tk.StringVar(value="None")
        for label in ("None", "Thirds", "Centre", "Diagonal"):
            ttk.Radiobutton(
                overlays_frame, text=label, value=label,
                variable=self._overlay_var,
                command=self._on_overlay_change,
            ).pack(side="left", padx=2)

        SectionHeader(p, "Focus Aids").pack(fill="x", pady=(8, 0))
        fp_frame = ttk.Frame(p, style="Panel.TFrame")
        fp_frame.pack(fill="x", padx=4, pady=2)
        self._fp_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            fp_frame, text="Focus Peaking", variable=self._fp_var,
            command=self._on_fp_toggle,
        ).pack(side="left")

        self._punchin_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            fp_frame, text="Punch-in (3×)", variable=self._punchin_var,
            command=self._on_punchin_toggle,
        ).pack(side="left", padx=8)

    def _build_tab_drive(self) -> None:
        p = self._make_tab("Drive")

        SectionHeader(p, "AEB").pack(fill="x", pady=(4, 0))
        ttk.Label(p, text="AEB bracket  (–1, 0, +1 EV)", style="Panel.TLabel").pack(
            anchor="w", padx=4,
        )
        ttk.Button(p, text="Shoot Bracket", command=self._shoot_aeb).pack(
            fill="x", padx=4, pady=2,
        )

        SectionHeader(p, "Intervalometer").pack(fill="x", pady=(8, 0))
        self._interval_slider = LabeledSlider(
            p, "Interval (s)", from_=1, to=60, initial=5, fmt="{:.0f} s",
        )
        self._interval_slider.pack(fill="x")

        self._frames_var = tk.IntVar(value=0)
        ttk.Label(p, text="Total frames (0 = ∞)", style="Panel.TLabel").pack(anchor="w", padx=4)
        ttk.Entry(p, textvariable=self._frames_var, width=6, font=FONT_SMALL).pack(
            anchor="w", padx=8,
        )

        tl_frame = ttk.Frame(p, style="Panel.TFrame")
        tl_frame.pack(fill="x", padx=4, pady=2)
        self._tl_btn = ttk.Button(tl_frame, text="▶ Start Time-lapse", command=self._toggle_timelapse)
        self._tl_btn.pack(fill="x")
        self._tl_count_var = tk.StringVar(value="")
        ttk.Label(tl_frame, textvariable=self._tl_count_var, style="Dim.TLabel").pack(anchor="w")

    def _build_tab_af(self) -> None:
        p = self._make_tab("AF")

        SectionHeader(p, "AF Mode").pack(fill="x", pady=(4, 0))
        af_mode_frame = ttk.Frame(p, style="Panel.TFrame")
        af_mode_frame.pack(fill="x", padx=4)
        self._af_mode_var = tk.StringVar(value="Manual")
        for label, mode in (("Manual", "Manual"), ("AF-S", "AF-S"), ("AF-C", "AF-C")):
            ttk.Radiobutton(
                af_mode_frame, text=label, value=mode,
                variable=self._af_mode_var,
                command=self._on_af_mode_change,
            ).pack(side="left", padx=4)

        SectionHeader(p, "Focus Area").pack(fill="x", pady=(8, 0))
        area_frame = ttk.Frame(p, style="Panel.TFrame")
        area_frame.pack(fill="x", padx=4)
        self._af_area_var = tk.StringVar(value="Wide")
        for label in ("Wide", "Zone", "Single"):
            ttk.Radiobutton(
                area_frame, text=label, value=label,
                variable=self._af_area_var,
                command=self._on_af_area_change,
            ).pack(side="left", padx=4)
        ttk.Label(p, text="(click preview to set point)", style="Dim.TLabel").pack(
            anchor="w", padx=8,
        )

        af_btn_frame = ttk.Frame(p, style="Panel.TFrame")
        af_btn_frame.pack(fill="x", padx=4, pady=2)
        ttk.Button(af_btn_frame, text="AF", command=self._trigger_af).pack(side="left", padx=2)
        ttk.Button(af_btn_frame, text="Home", command=self._home_lens).pack(side="left", padx=2)

        self._af_status_var = tk.StringVar(value="")
        ttk.Label(p, textvariable=self._af_status_var, style="Dim.TLabel").pack(anchor="w", padx=4)

        SectionHeader(p, "Manual Focus").pack(fill="x", pady=(8, 0))
        ttk.Label(p, text="Focus Step", style="Panel.TLabel").pack(anchor="w", padx=4)
        mf_frame = ttk.Frame(p, style="Panel.TFrame")
        mf_frame.pack(fill="x", padx=4, pady=2)
        for delta, label in ((-10, "◀◀"), (-1, "◀"), (+1, "▶"), (+10, "▶▶")):
            ttk.Button(
                mf_frame, text=label, width=4,
                command=lambda d=delta: self._manual_focus(d),
            ).pack(side="left", padx=1)

        self._mf_pos_var = tk.StringVar(value="Pos: 0")
        ttk.Label(p, textvariable=self._mf_pos_var, style="Dim.TLabel").pack(anchor="w", padx=4)

    # ------------------------------------------------------------------
    # Key bindings
    # ------------------------------------------------------------------

    def _bind_keys(self) -> None:
        self.bind("<space>",  lambda _: self._capture())
        self.bind("<f>",      lambda _: self._trigger_af())
        self.bind("<Left>",   lambda _: self._manual_focus(-1))
        self.bind("<Right>",  lambda _: self._manual_focus(+1))
        self.bind("<Shift-Left>",  lambda _: self._manual_focus(-10))
        self.bind("<Shift-Right>", lambda _: self._manual_focus(+10))

    # ------------------------------------------------------------------
    # Preview loop
    # ------------------------------------------------------------------

    def _update_preview(self) -> None:
        if not self._preview_running:
            return
        try:
            frame = self._cam.capture_frame()

            # Apply post-processing
            if self._active_matrix is not None:
                from camera.image_processing import apply_colour_matrix  # noqa: PLC0415
                frame = apply_colour_matrix(frame, self._active_matrix)

            if self._active_lut is not None:
                from camera.image_processing import apply_lut  # noqa: PLC0415
                frame = apply_lut(frame, self._active_lut)

            # Overlays
            ov = self._overlay_var.get()
            if ov == "Thirds":
                frame = draw_rule_of_thirds(frame)
            elif ov == "Centre":
                frame = draw_center_cross(frame)
            elif ov == "Diagonal":
                frame = draw_diagonal_grid(frame)

            if self._focus_peaking_on:
                frame = apply_focus_peaking(frame)

            if self._punchin_on:
                frame = digital_punchin(
                    frame,
                    cx=self._focus_roi_cx,
                    cy=self._focus_roi_cy,
                )

            # Draw focus-point indicator
            self._draw_focus_indicator(frame)

            # Update histogram
            draw_histogram(self._hist_canvas, frame, width=PREVIEW_W, height=HIST_H)

            # Show frame
            if PIL_AVAILABLE:
                img = Image.fromarray(frame)
                photo = ImageTk.PhotoImage(img)
                self._preview_canvas.create_image(0, 0, anchor="nw", image=photo)
                self._preview_canvas.image = photo   # keep reference
            else:
                self._preview_canvas.create_text(
                    PREVIEW_W // 2, PREVIEW_H // 2,
                    text="Preview requires Pillow", fill=FG, font=FONT_TITLE,
                )

            # Update MF position label
            self._mf_pos_var.set(f"Pos: {self._af.motor_position}")

        except Exception as exc:  # noqa: BLE001
            logger.debug("Preview frame error: %s", exc)

        self.after(50, self._update_preview)   # ~20 fps

    def _draw_focus_indicator(self, frame: np.ndarray) -> None:
        """Draw AF ROI box on the canvas overlay."""
        from autofocus.af_modes import build_roi, FocusArea  # noqa: PLC0415

        area_map = {"Wide": FocusArea.WIDE, "Zone": FocusArea.ZONE, "Single": FocusArea.SINGLE_POINT}
        area = area_map.get(self._af_area_var.get(), FocusArea.WIDE)
        roi = build_roi(area, PREVIEW_W, PREVIEW_H, self._focus_roi_cx, self._focus_roi_cy)
        self._preview_canvas.delete("af_box")
        if roi:
            x, y, w, h = roi
            colour = "#00ff00" if self._af.is_locked else "#ffcc00"
            self._preview_canvas.create_rectangle(
                x, y, x + w, y + h, outline=colour, width=2, tags="af_box",
            )

    # ------------------------------------------------------------------
    # Exposure handlers
    # ------------------------------------------------------------------

    def _on_shutter_change(self, event) -> None:  # noqa: ANN001
        label = self._shutter_combo.get()
        us = shutter_to_us(label)
        self._cam.set_shutter_speed(us)
        self._shutter_row.set_value(label)
        self._set_status(f"Shutter: {label}")

    def _on_iso_change(self, event) -> None:  # noqa: ANN001
        text = event.widget.get()
        iso = int(text.split()[-1])
        self._cam.set_iso(iso)
        self._set_status(f"ISO: {iso}")

    def _on_ev_change(self, value: float) -> None:
        rounded = round(round(value / 0.3) * 0.3, 1)
        self._cam.set_ev(rounded)
        self._set_status(f"EV: {ev_label(rounded)}")

    # ------------------------------------------------------------------
    # White balance handlers
    # ------------------------------------------------------------------

    def _on_wb_mode_change(self, event) -> None:  # noqa: ANN001
        label = self._wb_combo.get()
        mode = AWB_MODES[label]
        if mode == "manual":
            kelvin = int(self._kelvin_slider.get())
            r, b = kelvin_to_gains(kelvin)
            self._cam.set_manual_wb(r, b)
            self._set_status(f"WB: Manual {kelvin}K")
        else:
            self._cam.set_awb_mode(mode)
            self._set_status(f"WB: {label}")

    def _on_kelvin_change(self, value: float) -> None:
        if self._wb_combo.get() == "Manual":
            r, b = kelvin_to_gains(int(value))
            self._cam.set_manual_wb(r, b)
            self._set_status(f"WB: {int(value)} K")

    # ------------------------------------------------------------------
    # Image processing handlers
    # ------------------------------------------------------------------

    def _on_matrix_change(self, event) -> None:  # noqa: ANN001
        name = self._matrix_combo.get()
        self._active_matrix = None if name == "None" else COLOUR_MATRICES[name]
        self._set_status(f"Matrix: {name}")

    def _on_lut_change(self, event) -> None:  # noqa: ANN001
        name = self._lut_combo.get()
        self._active_lut = None if name == "None" else LUTS[name]
        self._set_status(f"LUT: {name}")

    # ------------------------------------------------------------------
    # Overlay / peaking handlers
    # ------------------------------------------------------------------

    def _on_overlay_change(self) -> None:
        self._set_status(f"Overlay: {self._overlay_var.get()}")

    def _on_fp_toggle(self) -> None:
        self._focus_peaking_on = self._fp_var.get()
        self._set_status(f"Focus peaking: {'on' if self._focus_peaking_on else 'off'}")

    def _on_punchin_toggle(self) -> None:
        self._punchin_on = self._punchin_var.get()
        self._set_status(f"Punch-in: {'on' if self._punchin_on else 'off'}")

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def _capture(self) -> None:
        self._set_status("Capturing …")
        self.update_idletasks()
        try:
            path = self._cam.capture_image()
            self._set_status(f"Saved: {path.name}")
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Capture error: {exc}")
            logger.error("Capture error: %s", exc)

    # ------------------------------------------------------------------
    # AEB
    # ------------------------------------------------------------------

    def _shoot_aeb(self) -> None:
        self._set_status("AEB: shooting bracket …")
        self.update_idletasks()
        try:
            paths = self._aeb.shoot()
            self._set_status(f"AEB: {len(paths)} frames saved")
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"AEB error: {exc}")

    # ------------------------------------------------------------------
    # Intervalometer
    # ------------------------------------------------------------------

    def _toggle_timelapse(self) -> None:
        if self._timer.running:
            self._timer.stop()
            self._tl_btn.configure(text="▶ Start Time-lapse")
            self._set_status("Time-lapse stopped")
        else:
            interval = self._interval_slider.get()
            total = self._frames_var.get()
            self._timer.start(interval_s=interval, total_frames=total)
            self._tl_btn.configure(text="⏹ Stop Time-lapse")
            self._set_status(f"Time-lapse: every {interval:.0f}s")

    def _on_timelapse_frame(self, path: str, count: int) -> None:
        self._tl_count_var.set(f"{count} frames")
        if not self._timer.running:
            self.after(0, lambda: self._tl_btn.configure(text="▶ Start Time-lapse"))

    # ------------------------------------------------------------------
    # Autofocus handlers
    # ------------------------------------------------------------------

    def _on_af_mode_change(self) -> None:
        mode_map = {
            "Manual": AFMode.MANUAL,
            "AF-S":   AFMode.AF_S,
            "AF-C":   AFMode.AF_C,
        }
        mode = mode_map[self._af_mode_var.get()]
        self._af.set_mode(mode)
        if mode == AFMode.AF_S:
            self._trigger_af()

    def _on_af_area_change(self) -> None:
        area_map = {
            "Wide":   FocusArea.WIDE,
            "Zone":   FocusArea.ZONE,
            "Single": FocusArea.SINGLE_POINT,
        }
        self._af.set_area(area_map[self._af_area_var.get()])

    def _trigger_af(self) -> None:
        if self._af.mode == AFMode.MANUAL:
            return
        self._set_status("AF: searching …")
        self._af_status_var.set("Searching …")
        self.update_idletasks()

        def _run() -> None:
            try:
                pos = self._af.trigger_afs()
                score = self._af.current_score
                self.after(0, lambda: self._af_status_var.set(
                    f"Locked  pos={pos}  sharpness={score:.1f}"
                ))
                self.after(0, lambda: self._set_status("AF: locked"))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self._af_status_var.set(f"AF error: {exc}"))

        threading.Thread(target=_run, daemon=True).start()

    def _home_lens(self) -> None:
        self._set_status("Homing lens …")
        self.update_idletasks()

        def _run() -> None:
            try:
                self._homing.home()
                self.after(0, lambda: self._set_status("Lens homed"))
                self.after(0, lambda: self._mf_pos_var.set("Pos: 0"))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self._set_status(f"Home error: {exc}"))

        threading.Thread(target=_run, daemon=True).start()

    def _manual_focus(self, delta: int) -> None:
        self._af.manual_step(delta)
        self._mf_pos_var.set(f"Pos: {self._af.motor_position}")

    # ------------------------------------------------------------------
    # Preview click – set focus point
    # ------------------------------------------------------------------

    def _on_preview_click(self, event: tk.Event) -> None:  # type: ignore[override]
        self._focus_roi_cx = event.x / PREVIEW_W
        self._focus_roi_cy = event.y / PREVIEW_H
        self._af.set_focus_point(self._focus_roi_cx, self._focus_roi_cy)
        logger.debug("Focus point set: (%.2f, %.2f)", self._focus_roi_cx, self._focus_roi_cy)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)

    def _on_close(self) -> None:
        self._preview_running = False
        self._timer.stop()
        self._af.stop()
        self._cam.close()
        self._motor.close()
        self.destroy()
