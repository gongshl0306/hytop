"""Color styles for the TUI: severity thresholds as pure functions.

Styles are plain names ("red"/"yellow"/"green"/"bold"); app.py maps them
to curses attributes (colors when the terminal supports them, bold/fallback
otherwise). VRAM is deliberately never colored: ~95% at idle is normal on
this driver (reserved HBM), an alarm would be a false positive.
"""

from __future__ import annotations

from typing import Optional

STYLE_NAMES = ("bold", "red", "yellow", "green", "cyan", "magenta")

TEMP_RED_C = 75.0
TEMP_YELLOW_C = 65.0

POWER_RED_FRAC = 0.9
POWER_YELLOW_FRAC = 0.8

UTIL_GREEN_PCT = 90.0

# bar gradient (nvitop-like): percent -> color of the filled blocks
BAR_GREEN_BELOW = 60.0
BAR_YELLOW_BELOW = 85.0

Style = Optional[str]


def temp_style(celsius: float | None) -> Style:
    if celsius is None:
        return None
    if celsius >= TEMP_RED_C:
        return "red"
    if celsius >= TEMP_YELLOW_C:
        return "yellow"
    return None


def power_style(power: float | None, cap: float | None) -> Style:
    if power is None or not cap:
        return None
    if power >= cap * POWER_RED_FRAC:
        return "red"
    if power >= cap * POWER_YELLOW_FRAC:
        return "yellow"
    return None


def util_style(percent: float | None) -> Style:
    if percent is None:
        return None
    return "green" if percent >= UTIL_GREEN_PCT else None


def bar_style(percent: float | None) -> Style:
    """Gradient for filled bar blocks: green -> yellow -> red by percent."""
    if percent is None:
        return None
    if percent >= BAR_YELLOW_BELOW:
        return "red"
    if percent >= BAR_GREEN_BELOW:
        return "yellow"
    return "green"
