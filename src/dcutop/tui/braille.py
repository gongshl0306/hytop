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
LEVELS_PER_CELL = 8

# One character = ONE sample (8 vertical levels via the two stacked text
# rows, both dot columns lit together). The waveform therefore shifts by
# exactly one full character per tick and glyph shapes stay stable.
LEVEL_BITS = (0xC0, 0x30, 0x0C, 0x03, 0xC0, 0x30, 0x0C, 0x03)  # bottom-up
# levels 0-3 live in the bottom text row, 4-7 in the top row


def _sample_glyph(level_pct: float) -> tuple[int, int]:
    """(bottom_row_bits, top_row_bits) for one sample value 0-100.

    A real value always lights at least the bottom row's lowest dots, so
    idle stretches draw a visible baseline; only gaps (None) stay blank.
    """
    filled = min(LEVELS_PER_CELL, max(1, round(level_pct / 100.0 * LEVELS_PER_CELL)))
    bottom = 0
    top = 0
    for level in range(filled):
        if level < 4:
            bottom |= LEVEL_BITS[level]
        else:
            top |= LEVEL_BITS[level]
    return bottom, top


def braille_chart(values: list[float | None], width: int,
                  prefill: bool = True) -> tuple[str, str]:
    """Two-row braille waveform for `values`, one sample per character.

    Time flows left to right: the right edge is now, and each new tick
    shifts the whole wave one full character. A young series is padded
    with its first sample (nvitop-style full-width flat start) unless
    `prefill` is off.
    """
    if width <= 0:
        return "", ""
    sampled = _downsample(values, width)
    if len(sampled) < width:
        filler = None
        if prefill:
            filler = next((v for v in sampled if v is not None), None)
        sampled = sampled + [filler] * (width - len(sampled))
    top_chars, bottom_chars = [], []
    for v in sampled:
        if v is None or v < 0:
            top_chars.append(BRAILLE_BLANK)
            bottom_chars.append(BRAILLE_BLANK)
            continue
        bottom, top = _sample_glyph(v)
        top_chars.append(chr(BRAILLE_BASE + top))
        bottom_chars.append(chr(BRAILLE_BASE + bottom))
    return "".join(top_chars), "".join(bottom_chars)


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


def hold_first(series: list[float | None], width: int) -> list[float | None]:
    """Pad a young series backwards with its first value.

    nvitop-style: at startup the chart is a full-width flat line at the
    first measured level and starts scrolling as samples accumulate,
    instead of showing a tiny dot cluster on an empty canvas.
    """
    if not series or len(series) >= width:
        return series
    first = next((v for v in series if v is not None), None)
    if first is None:
        return series
    return [first] * (width - len(series)) + series


def axis_line(width: int, interval_s: float = 1.0,
              marks: tuple[int, ...] = (120, 60, 30)) -> str:
    """Time-ago tick marks under a chart, e.g. `     |120s      |60s  |30s`."""
    if width <= 0 or interval_s <= 0:
        return ""
    span_s = width * interval_s
    pieces: list[str] = []
    for mark in marks:
        if mark <= span_s:
            column = width - int(mark / interval_s)
            pieces.append((column, f"|{mark}s"))
    if not pieces:
        return ""
    line: list[str] = []
    cursor = 0
    for column, label in pieces:
        start = max(cursor, column)
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
