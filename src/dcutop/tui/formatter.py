"""Value formatting for the TUI and text output. Pure functions.

Contract: ``None`` renders as ``N/A`` — never 0.
"""

from __future__ import annotations

NA = "N/A"

_SCALES = (("T", 1024**4), ("G", 1024**3), ("M", 1024**2), ("K", 1024))


def fmt_bytes(value) -> str:
    if value is None:
        return NA
    value = float(value)
    for unit, scale in _SCALES:
        if abs(value) >= scale:
            return f"{value / scale:.1f}{unit}"
    return f"{value:.0f}B"


def fmt_mem_pair(used, total) -> str:
    """'used/total' scaled to the unit of total, e.g. 13.2/14.4G."""
    if used is None and total is None:
        return NA
    if total is None:
        return f"{fmt_bytes(used)}/N/A"
    unit, scale = "G", 1024**3
    for u, s in _SCALES:
        if total >= s:
            unit, scale = u, s
            break
    else:
        unit, scale = "M", 1024**2
    used_part = NA if used is None else f"{used / scale:.1f}"
    return f"{used_part}/{total / scale:.1f}{unit}"


def fmt_percent(value, precision: int = 1) -> str:
    return NA if value is None else f"{value:.{precision}f}%"


def fmt_temp(value) -> str:
    return NA if value is None else f"{value:.1f}C"


def fmt_power(value) -> str:
    return NA if value is None else f"{value:.0f}W"


def fmt_clock(value) -> str:
    return NA if value is None else f"{value:.0f}M"


def fmt_user(value) -> str:
    return value if value else NA


def truncate(text: str | None, width: int) -> str:
    if text is None:
        return NA
    return text if len(text) <= width else text[: max(0, width - 1)] + "…"
