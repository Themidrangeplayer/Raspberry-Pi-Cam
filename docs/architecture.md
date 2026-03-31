# Architecture Overview

This document explains how the modules in Raspberry-Pi-Cam fit together and
how data flows through the application at runtime.

---

## High-level structure

```
┌─────────────────────────────────────────────────────────────────────┐
│  main.py  (entry point – CLI args, logging, wires subsystems)       │
└────────────────────────┬────────────────────────────────────────────┘
                         │ creates
          ┌──────────────▼──────────────┐
          │   ui/app.py  (CameraApp)    │  ← tkinter event loop
          │   live preview + controls   │
          └──┬─────────┬────────────────┘
             │         │
    ┌─────────▼──┐  ┌──▼─────────────────────────┐
    │  camera/   │  │        autofocus/            │
    │  package   │  │        package               │
    └────────────┘  └──────────────────────────────┘
```

The **UI layer** (`ui/`) owns the tkinter event loop and is the single
orchestrator.  Every subsystem is created in `CameraApp.__init__` and then
driven exclusively through UI callbacks (button presses, slider changes,
keyboard shortcuts, the periodic preview timer).

---

## Package-by-package breakdown

### `camera/` – Image acquisition and processing

| Module | Responsibility |
|--------|----------------|
| `capture.py` | `CameraManager` wraps `picamera2` (or `_StubCamera` on non-Pi hardware). Exposes `capture_frame()` for the live preview and `capture_image()` for full-resolution stills. |
| `exposure.py` | Lookup tables and conversion helpers for shutter speed (1/8000 s – 30 s), ISO (100–3200), and EV compensation (±3 EV in ⅓ stops). No state – pure functions and constants. |
| `white_balance.py` | AWB preset names and a `kelvin_to_gains(k)` function that linearly interpolates a calibration table to produce red/blue gain pairs. |
| `image_processing.py` | 3×3 colour matrices (Identity, Vivid, Cool, Warm) and 1-D per-channel LUTs (Identity, S-Curve). `apply_colour_matrix()` and `apply_lut()` operate on raw `numpy` arrays. |
| `drive_modes.py` | `AEBController` captures a bracketed burst by temporarily overriding EV; `Intervalometer` fires the shutter at a fixed interval in a daemon thread. |

**Data flow for a preview frame:**

```
picamera2 / _StubCamera
        │  capture_array() → HxWx3 uint8 RGB
        ▼
CameraManager.capture_frame()
        │
        ▼
[optional] apply_colour_matrix()   ← camera/image_processing.py
        │
        ▼
[optional] apply_lut()             ← camera/image_processing.py
        │
        ▼
[optional] apply_focus_peaking()   ← ui/overlays.py
        │
        ▼
[optional] digital_punchin()       ← ui/overlays.py
        │
        ▼
[optional] draw_rule_of_thirds()   ← ui/overlays.py
        │
        ▼
draw_histogram()                   ← ui/histogram.py  (side channel)
        │
        ▼
PIL.ImageTk → tkinter Canvas       ← ui/app.py  (displayed every ~33 ms)
```

---

### `autofocus/` – Motorised lens control

| Module | Responsibility |
|--------|----------------|
| `motor.py` | `create_driver(type)` factory returns one of four driver objects: `_StubDriver` (software-only), `_GPIODriver` (RPi.GPIO stepper, pins 23/24 by default), `_I2CDriver` (DRV8830-style, SMBus), `_SPIDriver` (L6470 dSPIN). All share the same interface: `step(n, direction)`, `position`. |
| `cdaf.py` | `CDAFController.run_once(capture_fn, roi)` performs a two-pass hill-climb: a *coarse* forward sweep followed by a *fine* sweep centred on the coarse best position. Sharpness is measured via the variance of the Laplacian over the ROI. |
| `calibration.py` | `HomingController.home()` drives the motor backward until a limit switch trips, then zeros the position counter. `FocusCalibration` stores a piecewise-linear map of motor positions → focus distances (cm). |
| `af_modes.py` | `AFController` is the top-level state machine. It holds the current `AFMode` (MANUAL / AF-S / AF-C), the `FocusArea` (WIDE / ZONE / SINGLE_POINT), and coordinates `CDAFController` and the motor driver. AF-C runs `CDAFController.run_once()` in a daemon thread on a configurable interval. |

**Autofocus sequence (AF-S):**

```
User presses 'F' (or clicks AF button)
        │
AFController.trigger_afs()
        │
CDAFController.run_once(capture_fn, roi)
        │
    ┌───▼────────────────────────────────────────┐
    │  Coarse sweep (N forward motor steps)       │
    │    ├─ motor.step(1, FORWARD)                │
    │    └─ score = measure_sharpness(frame, roi) │
    │  Move to coarse best position               │
    │                                             │
    │  Fine sweep (±fine_steps around best)       │
    │    ├─ motor.step(1, FORWARD) × (2·fine_steps+1) │
    │    └─ score = measure_sharpness(frame, roi) │
    │  Move to fine best position                 │
    └─────────────────────────────────────────────┘
        │
AFController._locked = True
```

---

### `ui/` – User interface

| Module | Responsibility |
|--------|----------------|
| `app.py` | `CameraApp(tk.Tk)` – the main window.  Layout: 640×480 live preview canvas on the left, 120-px histogram strip below it, a scrollable 280-px control panel on the right, and a status bar at the bottom.  A `after(33, _update_preview)` timer drives the ~30 fps preview loop. |
| `histogram.py` | `compute_histogram(frame)` returns normalised per-channel bin counts; `draw_histogram(canvas, frame, …)` renders them as overlapping R/G/B curves on a tkinter `Canvas`. |
| `overlays.py` | Pure-function image compositors: `draw_rule_of_thirds`, `draw_center_cross`, `draw_diagonal_grid`, `apply_focus_peaking`, `digital_punchin`. All take and return `numpy` arrays. |
| `widgets.py` | Dark-theme colour palette constants and reusable compound widgets: `SettingRow`, `CycleButton` (cycles through a list), `LabeledSlider`, `SectionHeader`. |

**Preview loop (runs every 33 ms):**

```
CameraApp._update_preview()
    │
    ├─ camera.capture_frame()           → raw RGB frame
    ├─ apply_colour_matrix(frame, …)    (if matrix ≠ identity)
    ├─ apply_lut(frame, …)              (if LUT ≠ identity)
    ├─ apply_focus_peaking(frame, …)    (if focus peaking ON)
    ├─ digital_punchin(frame, …)        (if punch-in ON)
    ├─ draw_overlay(frame, …)           (if composition overlay ON)
    ├─ _draw_focus_indicator(frame)     (AF ROI box + lock indicator)
    ├─ PIL.Image.fromarray → ImageTk    (convert for tkinter)
    ├─ canvas.create_image(…)           (display)
    └─ draw_histogram(hist_canvas, …)   (update histogram strip)
```

---

## Stub / hardware fallback strategy

The application deliberately avoids crashing when hardware is absent:

| Hardware | Availability check | Fallback |
|----------|--------------------|---------|
| `picamera2` | `try: import picamera2` | `_StubCamera` generates a synthetic RGB gradient |
| `RPi.GPIO` | `try: import RPi.GPIO` | `_StubDriver` counts motor steps in software |
| `smbus2` | `try: import smbus2` | `create_driver("i2c")` returns `_StubDriver` with a warning |
| `spidev` | `try: import spidev` | `create_driver("spi")` returns `_StubDriver` with a warning |

This means `python main.py` (no flags) always works on a development laptop.

---

## Threading model

The application is mostly single-threaded (tkinter's event loop), with two
well-defined exceptions:

| Thread | Owner | Purpose |
|--------|-------|---------|
| `Intervalometer._run` | `camera/drive_modes.py` | Fires `camera.capture_image()` at the configured interval; posts results back via an `on_capture` callback (safe to call from non-main thread). |
| `AFController._afc_thread` | `autofocus/af_modes.py` | Runs `CDAFController.run_once()` continuously in AF-C mode; protected by `threading.Lock` against concurrent preview reads. |

All other operations (exposure changes, WB updates, AEB bursts, manual focus
steps) happen synchronously in the tkinter callback thread.
