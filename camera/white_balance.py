"""
white_balance.py – White balance presets and manual gain helpers.

Provides AWB mode labels and a Kelvin→gain conversion so the UI can
offer both preset and manual (colour-temperature) white balance.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# AWB mode map  (label → picamera2 mode string)
# ---------------------------------------------------------------------------

AWB_MODES: Dict[str, str] = {
    "Auto":          "auto",
    "Daylight":      "daylight",
    "Cloudy":        "cloudy",
    "Shade":         "shade",
    "Tungsten":      "tungsten",
    "Fluorescent":   "fluorescent",
    "Indoor":        "indoor",
    "Manual":        "manual",
}

AWB_LABELS: List[str] = list(AWB_MODES.keys())


# ---------------------------------------------------------------------------
# Kelvin ↔ Gain conversion
# ---------------------------------------------------------------------------

# Approximate (R_gain, B_gain) pairs at representative colour temperatures.
# Interpolated linearly for values in between.
_KELVIN_TABLE: List[Tuple[int, float, float]] = [
    (2500, 2.00, 1.00),
    (3200, 1.80, 1.10),
    (4000, 1.50, 1.30),
    (5200, 1.25, 1.50),
    (5500, 1.20, 1.55),
    (6500, 1.10, 1.65),
    (7500, 1.00, 1.80),
]

KELVIN_MIN = _KELVIN_TABLE[0][0]
KELVIN_MAX = _KELVIN_TABLE[-1][0]


def kelvin_to_gains(kelvin: int) -> Tuple[float, float]:
    """Return (r_gain, b_gain) for the given colour temperature in Kelvin."""
    kelvin = max(KELVIN_MIN, min(KELVIN_MAX, kelvin))
    for i in range(len(_KELVIN_TABLE) - 1):
        k0, r0, b0 = _KELVIN_TABLE[i]
        k1, r1, b1 = _KELVIN_TABLE[i + 1]
        if k0 <= kelvin <= k1:
            t = (kelvin - k0) / (k1 - k0)
            return (r0 + t * (r1 - r0), b0 + t * (b1 - b0))
    # Shouldn't reach here, but be safe
    _, r, b = _KELVIN_TABLE[-1]
    return (r, b)
