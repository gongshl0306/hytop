"""Braille dot-matrix charts — the nvitop-style waveform rendering.

A chart is two text rows of braille cells; each cell is a 2x4 dot matrix,
so a column resolves 8 vertical levels. A value pinned at 100% reads as a
dense dot field, not a solid rectangle.

Level -> dot-bit mapping (bottom-up, left column then right column):
    levels 0-3 (bottom text row):  0x01, 0x04, 0x10, 0x40
    levels 4-7 (top text row):     0x02, 0x08, 0x20, 0x80
"""

from __future__ import annotations

BRAILLE_BASE = 0x2800
BRAILLE_BLANK = chr(BRAILLE_BASE)
LEVEL_BITS_BOTTOM = (0x01, 0x04, 0x10, 0x40)
LEVEL_BITS_TOP = (0x02, 0x08, 0x20, 0x80)
LEVELS_PER_CELL = 8


def _downsample(values: list[float | None], width: int) -> list[float | None]:
    if width <= 0 or len(values) <= width:
        return list(values)
    bucket = len(values) / width
    out: list[float | None] = []
    for i in range(width):
        start = int(i * bucket)
        end = max(start + 1, int((i + 1) * bucket))
        real = [v for v in values[start:end] if v is not None and v >= 0]
        out.append(sum(real) / len(real) if real else None)
    return out


def _column_cells(level: float) -> tuple[int, int]:
    """Dot bitmasks (bottom_row, top_row) for one sampled value 0-100.

    A real value always lights at least the bottom dot, so idle stretches
    draw a visible baseline; only gaps (None) render fully blank.
    """
    filled = min(LEVELS_PER_CELL, max(1, round(level / 100.0 * LEVELS_PER_CELL)))
    bottom = 0
    for i in range(min(4, filled)):
        bottom |= LEVEL_BITS_BOTTOM[i]
    top = 0
    for i in range(4, filled):
        top |= LEVEL_BITS_TOP[i - 4]
    return bottom, top


def braille_chart(values: list[float | None], width: int) -> tuple[str, str]:
    """Two-row braille waveform for `values`, padded to `width` cells.

    Older samples scroll left as new ones arrive; the empty right part of
    a young chart renders as blank braille cells so the canvas keeps a
    constant grid.
    """
    if width <= 0:
        return "", ""
    sampled = _downsample(values, width)
    sampled = sampled + [None] * (width - len(sampled))
    bottom_chars, top_chars = [], []
    for v in sampled:
        if v is None or v < 0:
            bottom_chars.append(BRAILLE_BLANK)
            top_chars.append(BRAILLE_BLANK)
            continue
        bottom, top = _column_cells(v)
        bottom_chars.append(chr(BRAILLE_BASE + bottom))
        top_chars.append(chr(BRAILLE_BASE + top))
    return "".join(top_chars), "".join(bottom_chars)


def axis_line(width: int, interval_s: float = 1.0,
              marks: tuple[int, ...] = (120, 60, 30)) -> str:
    """Time-ago labels under a chart, e.g. `        120s       60s   30s`."""
    if width <= 0 or interval_s <= 0:
        return ""
    span_s = width * interval_s
    pieces: list[str] = []
    for mark in marks:
        if mark <= span_s:
            column = width - int(mark / interval_s)
            label = f"{mark}s"
            pieces.append((column, label))
    if not pieces:
        return ""
    line: list[str] = []
    cursor = 0
    for column, label in pieces:
        start = max(cursor, column - len(label))
        line.append(" " * (start - cursor))
        line.append(label)
        cursor = start + len(label)
    return "".join(line)


def avg_series(series_by_device: dict[int, list[float | None]]) -> list[float | None]:
    """Point-wise average across devices (None where no device has data)."""
    length = max((len(s) for s in series_by_device.values()), default=0)
    out: list[float | None] = []
    for i in range(length):
        real = [s[i] for s in series_by_device.values()
                if i < len(s) and s[i] is not None]
        out.append(sum(real) / len(real) if real else None)
    return out
