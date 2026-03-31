"""
widgets.py – Reusable tkinter widgets for the camera UI.

Palette & style constants live here so every widget uses the same look.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

BG        = "#1e1e1e"
BG_PANEL  = "#2a2a2a"
BG_ACTIVE = "#3a3a3a"
FG        = "#e0e0e0"
FG_DIM    = "#888888"
ACCENT    = "#e85c1a"
BORDER    = "#444444"

FONT_LABEL  = ("Helvetica", 9)
FONT_VALUE  = ("Helvetica", 11, "bold")
FONT_TITLE  = ("Helvetica", 10, "bold")
FONT_SMALL  = ("Helvetica", 8)


def configure_styles() -> None:
    """Apply global ttk style settings."""
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TFrame",       background=BG)
    style.configure("Panel.TFrame", background=BG_PANEL)
    style.configure("TLabel",       background=BG,       foreground=FG,     font=FONT_LABEL)
    style.configure("Panel.TLabel", background=BG_PANEL, foreground=FG,     font=FONT_LABEL)
    style.configure("Value.TLabel", background=BG_PANEL, foreground=ACCENT, font=FONT_VALUE)
    style.configure("Dim.TLabel",   background=BG_PANEL, foreground=FG_DIM, font=FONT_SMALL)
    style.configure(
        "TButton",
        background=BG_PANEL, foreground=FG,
        borderwidth=1, relief="flat", padding=4,
    )
    style.map("TButton",
        background=[("active", BG_ACTIVE), ("pressed", ACCENT)],
        foreground=[("pressed", "#ffffff")],
    )
    style.configure(
        "Accent.TButton",
        background=ACCENT, foreground="#ffffff",
        borderwidth=0, relief="flat", padding=6, font=FONT_TITLE,
    )
    style.map("Accent.TButton",
        background=[("active", "#ff7030")],
    )
    style.configure(
        "TScale",
        background=BG_PANEL, troughcolor="#3a3a3a",
        sliderlength=12, sliderrelief="flat",
    )
    style.configure(
        "TCombobox",
        fieldbackground=BG_PANEL, background=BG_PANEL,
        foreground=FG, selectbackground=ACCENT,
    )
    style.configure(
        "Horizontal.TSeparator",
        background=BORDER,
    )


# ---------------------------------------------------------------------------
# SettingRow – label + value + optional control in one horizontal strip
# ---------------------------------------------------------------------------

class SettingRow(ttk.Frame):
    """
    A compact row showing:  [Label]  [Value]  [optional widget]
    """

    def __init__(
        self,
        parent,
        label: str,
        value: str = "",
        *,
        style: str = "Panel.TFrame",
    ) -> None:
        super().__init__(parent, style=style, padding=(4, 2))
        self._label_var = tk.StringVar(value=label)
        self._value_var = tk.StringVar(value=value)

        ttk.Label(self, textvariable=self._label_var, style="Panel.TLabel", width=14,
                  anchor="w").pack(side="left")
        ttk.Label(self, textvariable=self._value_var, style="Value.TLabel", width=10,
                  anchor="e").pack(side="left", padx=(2, 0))

    def set_value(self, value: str) -> None:
        self._value_var.set(value)

    def get_value(self) -> str:
        return self._value_var.get()


# ---------------------------------------------------------------------------
# CycleButton – click to cycle through a list of options
# ---------------------------------------------------------------------------

class CycleButton(ttk.Button):
    """Button that cycles through a fixed list of string options."""

    def __init__(
        self,
        parent,
        options: List[str],
        on_change: Optional[Callable[[str], None]] = None,
        **kw,
    ) -> None:
        self._options = list(options)
        self._index = 0
        self._on_change = on_change
        super().__init__(parent, text=self._options[0], command=self._cycle, **kw)

    def _cycle(self) -> None:
        self._index = (self._index + 1) % len(self._options)
        self.configure(text=self._options[self._index])
        if self._on_change:
            self._on_change(self._options[self._index])

    def set_option(self, option: str) -> None:
        if option in self._options:
            self._index = self._options.index(option)
            self.configure(text=option)

    @property
    def current(self) -> str:
        return self._options[self._index]


# ---------------------------------------------------------------------------
# LabeledSlider – a slider with live value label
# ---------------------------------------------------------------------------

class LabeledSlider(ttk.Frame):
    def __init__(
        self,
        parent,
        label: str,
        from_: float,
        to: float,
        initial: float = 0.0,
        resolution: float = 1.0,
        fmt: str = "{:.0f}",
        on_change: Optional[Callable[[float], None]] = None,
        *,
        style: str = "Panel.TFrame",
    ) -> None:
        super().__init__(parent, style=style, padding=(4, 2))
        self._fmt = fmt
        self._on_change = on_change
        self._var = tk.DoubleVar(value=initial)

        ttk.Label(self, text=label, style="Panel.TLabel", width=14,
                  anchor="w").pack(side="left")

        self._val_label = ttk.Label(
            self, text=self._fmt.format(initial),
            style="Value.TLabel", width=7, anchor="e",
        )
        self._val_label.pack(side="right")

        slider = ttk.Scale(
            self, from_=from_, to=to, variable=self._var,
            orient="horizontal",
            command=self._on_slider,
        )
        slider.pack(side="left", fill="x", expand=True, padx=4)
        self._slider = slider

    def _on_slider(self, _: str) -> None:
        v = self._var.get()
        self._val_label.configure(text=self._fmt.format(v))
        if self._on_change:
            self._on_change(v)

    def get(self) -> float:
        return self._var.get()

    def set(self, value: float) -> None:
        self._var.set(value)
        self._val_label.configure(text=self._fmt.format(value))


# ---------------------------------------------------------------------------
# SectionHeader – dark title bar for panel sections
# ---------------------------------------------------------------------------

class SectionHeader(tk.Frame):
    def __init__(self, parent, title: str) -> None:
        super().__init__(parent, bg=BORDER, pady=2)
        tk.Label(self, text=title.upper(), bg=BORDER, fg=FG_DIM,
                 font=FONT_SMALL).pack(side="left", padx=8)
