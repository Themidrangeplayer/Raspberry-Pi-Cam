"""
exposure.py – Shutter speed, ISO, and Exposure Compensation helpers.

All arithmetic stays in this module so the rest of the application can
use clean helper methods without repeating conversion logic.
"""

from __future__ import annotations

from typing import List

# ---------------------------------------------------------------------------
# Shutter speed tables
# ---------------------------------------------------------------------------

# Canonical shutter speed denominators (1/N s).  The list spans from very
# fast to bulb exposures.
SHUTTER_DENOMINATORS: List[int] = [
    8000, 4000, 3200, 2000, 1600, 1250, 1000, 800, 640, 500,
    400, 320, 250, 200, 160, 125, 100, 80, 60, 50, 40, 30, 25,
    20, 15, 13, 10, 8, 6, 5, 4, 3, 2,
]
# Also include whole-second values (1s, 2s …30s) stored as negative ints.
SHUTTER_WHOLE_SECONDS: List[int] = [1, 2, 3, 4, 5, 6, 8, 10, 13, 15, 20, 25, 30]


def shutter_label(microseconds: int) -> str:
    """Return a human-readable label for a shutter speed in microseconds."""
    seconds = microseconds / 1_000_000
    if seconds >= 1.0:
        if seconds.is_integer():
            return f'{int(seconds)}"'
        return f'{seconds:.1f}"'
    denom = round(1.0 / seconds)
    return f"1/{denom}"


def shutter_to_us(label: str) -> int:
    """
    Convert a shutter speed label such as '1/250' or '2"' to microseconds.
    """
    label = label.strip().rstrip('"')
    if "/" in label:
        num, den = label.split("/")
        return int(float(num) / float(den) * 1_000_000)
    return int(float(label) * 1_000_000)


def all_shutter_labels() -> List[str]:
    """Return the full sorted list of shutter speed labels (slowest first)."""
    labels = [f'{s}"' for s in reversed(SHUTTER_WHOLE_SECONDS)]
    labels += [f"1/{d}" for d in SHUTTER_DENOMINATORS]
    return labels


# ---------------------------------------------------------------------------
# ISO helpers
# ---------------------------------------------------------------------------

ISO_VALUES: List[int] = [100, 200, 400, 800, 1600, 3200]


def iso_label(iso: int) -> str:
    return f"ISO {iso}"


# ---------------------------------------------------------------------------
# EV / Exposure Compensation
# ---------------------------------------------------------------------------

EV_MIN = -3.0
EV_MAX = 3.0
EV_STEP = 0.3   # 1/3 stop increments


def ev_steps() -> List[float]:
    """Return the discrete EV compensation values in 1/3-stop steps."""
    steps = []
    v = EV_MIN
    while v <= EV_MAX + 1e-9:
        steps.append(round(v, 1))
        v += EV_STEP
    return steps


def ev_label(ev: float) -> str:
    if ev == 0.0:
        return "±0 EV"
    sign = "+" if ev > 0 else ""
    return f"{sign}{ev:.1f} EV"
