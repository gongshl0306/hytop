"""Frame rendering for the TUI — pure functions, no curses here.

A frame is a list of lines; each line is a list of ``(text, style)``
segments. Layout follows the nvitop look: aligned tabular device panel
with solid gradient bars, aggregate braille charts with time axis, and
titled sections. All column widths derive from one layout object so the
header and rows always line up.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass

import hytop
from hytop.tui.braille import avg_series, axis_line, braille_chart, hold_first
from hytop.tui.formatter import (
    NA,
    fmt_bytes,
    fmt_clock,
    fmt_mem_pair,
    fmt_percent,
    fmt_power,
    fmt_temp,
    truncate,
)
from hytop.tui.theme import bar_style, power_style, temp_style

Segment = tuple[str, str | None]
Line = list[Segment]

SORT_KEYS = ("pid", "vram", "cu", "cpu")

BAR_CAP = "▏"  # thin marker so a 0% bar is still visible
PROCESS_HEADER = (
    f"{'PID':>7}  {'USER':<8} {'HCU':>3} {'VRAM':>7} {'CU%':>5} "
    f"{'CPU%':>6} {'MEM%':>5}  COMMAND"
)

HELP_LINE = (
    "q quit | r refresh | up/down select | p sort PID | m sort VRAM | "
    "c sort CU | u sort CPU | 1-9 filter HCU | a all"
)


@dataclass(frozen=True)
class DeviceLayout:
    """Column spans for the device panel; header and rows share it."""

    width: int
    util_bar: int = 16
    mem_bar: int = 14

    UTIL_FIXED = 8  # cap + gap + "100.0%"
    MEM_FIXED = 14  # cap + gap + "136.2/144.0G"
    TABLE_FIXED = 84  # everything except the two bar cells

    def util_cell_width(self) -> int:
        return self.util_bar + self.UTIL_FIXED

    def mem_cell_width(self) -> int:
        return self.mem_bar + self.MEM_FIXED

    @classmethod
    def for_width(cls, width: int) -> "DeviceLayout":
        """Size the two bar columns so the table exactly fills `width`.

        The rest of the table has a fixed span; measure it from a probe
        header instead of hand-maintaining the constant.
        """
        base = len(text_of(cls(width=width).header()))
        extra = width - base
        util, mem = cls.util_bar, cls.mem_bar
        if extra >= 0:
            util += extra // 2
            mem += extra - extra // 2
        else:
            util = max(6, util + extra // 2)
            mem = max(6, mem + (extra - extra // 2))
        return cls(width=width, util_bar=util, mem_bar=mem)

    def header(self) -> Line:
        text = (
            f"{'HCU':>3}  {'Model':<10}  {'Temp':>6}  {'Power':>7}  "
            f"{'HCU%':<{self.util_cell_width()}}  {'CU%':>6}  "
            f"{'VRAM':<{self.mem_cell_width()}}  {'SCLK':>6}  {'MCLK':>6}"
        )
        return [(text, "bold")]

    def bar_cell(self, value: float | None, bar_width: int, suffix: str) -> tuple[str, str | None]:
        """`▏█████     82.1%` — solid gradient blocks, blank filler."""
        style = bar_style(value)
        if value is None:
            blocks = ""
        else:
            filled = int(round(min(1.0, max(0.0, value / 100.0)) * bar_width))
            blocks = "█" * filled
        text = f"{BAR_CAP}{blocks:<{bar_width}} {suffix}"
        return text, style


@dataclass
class TuiState:
    process_sort: str = "pid"
    filter_devices: set | None = None
    selected: int = 0


def text_of(line: Line) -> str:
    """Plain text of a line (headless printing, tests)."""
    return "".join(text for text, _ in line)


def handle_key(state: TuiState, key: int, device_count: int) -> str | None:
    """Key state machine; returns 'quit' or None after mutating state.

    Sort keys pick the process-table sort. Digits toggle devices in/out of
    the process filter (None = show all); 'a' clears the filter.
    """
    import curses

    if key in (ord("q"), 27):  # q or ESC
        return "quit"
    if key == ord("p"):
        state.process_sort = "pid"
    elif key == ord("m"):
        state.process_sort = "vram"
    elif key == ord("c"):
        state.process_sort = "cu"
    elif key == ord("u"):
        state.process_sort = "cpu"
    elif key == ord("a"):
        state.filter_devices = None
    elif ord("1") <= key <= ord("9"):
        index = key - ord("1")
        if index < device_count:
            current = set(state.filter_devices) if state.filter_devices else set()
            if index in current:
                current.discard(index)
            else:
                current.add(index)
            state.filter_devices = current or None
    elif key == curses.KEY_UP:
        state.selected = max(0, state.selected - 1)
    elif key == curses.KEY_DOWN:
        state.selected += 1  # clamped against row count at render time
    return None


def short_model(name: str | None) -> str:
    if not name:
        return NA
    for prefix in ("HYGON ", "MOCK "):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name[:10]


def device_lines(snapshot, layout: DeviceLayout) -> list[Line]:
    lines: list[Line] = [layout.header()]
    for index in sorted(snapshot.devices):
        m = snapshot.devices[index]
        info = snapshot.device_info.get(index)
        model = short_model(info.name if info else None)
        temp = m.temperature.edge

        mem_fraction = None
        if m.memory_used is not None and m.memory_total:
            mem_fraction = m.memory_used / m.memory_total * 100.0
        util_text, util_style_ = layout.bar_cell(
            m.utilization, layout.util_bar, f"{fmt_percent(m.utilization):>6}"
        )
        mem_text, mem_style_ = layout.bar_cell(
            mem_fraction, layout.mem_bar,
            f"{fmt_mem_pair(m.memory_used, m.memory_total):>12}",
        )
        line: Line = [
            (f"{index:>3}  {model:<10}  ", None),
            (f"{fmt_temp(temp):>6}", temp_style(temp)),
            ("  ", None),
            (f"{fmt_power(m.power):>7}", power_style(m.power, m.power_cap)),
            ("  ", None),
            (util_text, util_style_),
            ("  ", None),
            (f"{fmt_percent(m.cu_utilization):>6}", None),
            ("  ", None),
            (mem_text, mem_style_),
            ("  ", None),
            (f"{fmt_clock(m.sclk_mhz):>6}", None),
            ("  ", None),
            (f"{fmt_clock(m.mclk_mhz):>6}", None),
        ]
        lines.append(line)
    return lines


def _mem_fraction_series(history, total: int | None) -> list[float | None]:
    values = history.memory_used.values() if history else []
    if not total:
        return [None] * len(values)
    return [None if v is None else v / total * 100.0 for v in values]


def chart_lines(snapshot, width: int, interval_s: float) -> list[Line]:
    """Aggregate AVG GPU UTL (cyan) and AVG GPU MEM (yellow) braille charts."""
    chart_width = min(80, max(24, width - 6))
    lines: list[Line] = []

    util_series = hold_first(
        avg_series({i: list(h.utilization.values()) for i, h in snapshot.history.items()}),
        chart_width,
    )
    mem_series = hold_first(
        avg_series(
            {
                i: _mem_fraction_series(h, snapshot.devices[i].memory_total if i in snapshot.devices else None)
                for i, h in snapshot.history.items()
            }
        ),
        chart_width,
    )

    def caption(label: str, series) -> Line:
        real = [v for v in series if v is not None]
        avg = f"{sum(real) / len(real):.1f}%" if real else NA
        return [(f"{label}: {avg}", "bold")]

    util_top, util_bottom = braille_chart(util_series, chart_width)
    mem_top, mem_bottom = braille_chart(mem_series, chart_width)

    lines.append(caption("AVG GPU UTL", util_series))
    lines.append([(util_top, "cyan")])
    lines.append([(util_bottom, "cyan")])
    lines.append(caption("AVG GPU MEM", mem_series))
    lines.append([(mem_top, "yellow")])
    lines.append([(mem_bottom, "yellow")])
    axis = axis_line(chart_width, interval_s)
    if axis:
        lines.append([(axis, None)])
    return lines


def _sort_processes(snapshot, state: TuiState):
    rows = []
    for proc in snapshot.processes:
        if state.filter_devices and not (set(proc.devices) & state.filter_devices):
            continue
        for dev_index, usage in sorted(proc.devices.items()):
            if state.filter_devices and dev_index not in state.filter_devices:
                continue
            rows.append((proc, dev_index, usage))
    key = state.process_sort
    if key == "vram":
        rows.sort(key=lambda r: r[2].vram_used if r[2].vram_used is not None else -1, reverse=True)
    elif key == "cu":
        rows.sort(key=lambda r: r[2].cu_occupancy if r[2].cu_occupancy is not None else -1, reverse=True)
    elif key == "cpu":
        rows.sort(key=lambda r: r[0].cpu_percent if r[0].cpu_percent is not None else -1, reverse=True)
    else:
        rows.sort(key=lambda r: (r[0].pid, r[1]))
    return rows


def process_lines(snapshot, state: TuiState, width: int = 120) -> list[Line]:
    rows = _sort_processes(snapshot, state)
    if not rows:
        return [[(PROCESS_HEADER, "bold")], [("  (no HCU processes)", None)]]
    lines: list[Line] = [[(PROCESS_HEADER, "bold")]]
    for position, (proc, dev_index, usage) in enumerate(rows):
        marker = ">" if position == state.selected else " "
        vram = fmt_bytes(usage.vram_used)
        cu = NA if usage.cu_occupancy is None else f"{usage.cu_occupancy:.1f}"
        cpu = NA if proc.cpu_percent is None else f"{proc.cpu_percent:.1f}"
        mem = NA if proc.host_memory_percent is None else f"{proc.host_memory_percent:.1f}"
        command = truncate(proc.command or proc.name, max(8, width - 50))
        style = "bold" if position == state.selected else None
        lines.append([(
            f"{marker}{proc.pid:>7}  {(proc.username or NA)[:8]:<8} {dev_index:>3} "
            f"{vram:>7} {cu:>5} {cpu:>6} {mem:>5}  {command}",
            style,
        )])
    return lines


def _box_top(title: str, width: int) -> Line:
    if title:
        fill = max(0, width - 5 - len(title))
        return [(f"┌─ {title} " + "─" * fill + "┐", None)]
    return [("┌" + "─" * max(0, width - 2) + "┐", None)]


def _box_bottom(width: int) -> Line:
    return [("└" + "─" * max(0, width - 2) + "┘", None)]


def _box_sep(width: int) -> Line:
    return [("├" + "─" * max(0, width - 2) + "┤", None)]


def _box_row(line: Line, width: int) -> Line:
    """`│ content(pad) │` — one content line inside the box."""
    inner = max(0, width - 4)
    text_len = sum(len(text) for text, _ in line)
    pad = max(0, inner - text_len)
    return [("│ ", None)] + line + [(" " * pad + " │", None)]


def _box(lines: list[Line], width: int, title: str = "") -> list[Line]:
    out: list[Line] = [_box_top(title, width)]
    for line in lines:
        out.append(_box_row(line, width))
    out.append(_box_bottom(width))
    return out


def render_frame(snapshot, state: TuiState, width: int = 120,
                 interval_s: float = 1.0, height: int | None = None) -> list[Line]:
    errors = snapshot.errors
    stamp = time.strftime("%b %d %H:%M:%S", time.localtime(snapshot.timestamp))
    title = (
        f"hytop {hytop.__version__}  host: {socket.gethostname()}  "
        f"devices: {len(snapshot.devices)}  {stamp}"
    )
    if snapshot.cpu_percent is not None:
        title += (
            f"  host cpu {fmt_percent(snapshot.cpu_percent)}  "
            f"mem {fmt_percent(snapshot.memory_percent)}"
        )
    if errors:
        title += f"  errors: {len(errors)}"

    layout = DeviceLayout.for_width(width - 4)  # boxes eat "│ " and " │"
    device_rows = device_lines(snapshot, layout)

    # top + bottom borders, header + data rows, separator after every row
    # except the last
    devices_height = 2 + len(device_rows) + max(0, len(device_rows) - 1)
    charts = chart_lines(snapshot, width - 4, interval_s)
    charts_height = len(charts) + 2
    processes = process_lines(snapshot, state, width=width - 4)
    processes_height = len(processes) + 2
    fixed_height = 5  # info box + help + error line

    include_charts = True
    if height is not None:
        needed = fixed_height + devices_height + processes_height
        include_charts = needed + charts_height <= height

    frame: list[Line] = _box([[ (title, "bold") ]], width)
    frame.append(_box_top("Devices", width))
    for position, row in enumerate(device_rows):
        frame.append(_box_row(row, width))
        if position < len(device_rows) - 1:
            frame.append(_box_sep(width))
    frame.append(_box_bottom(width))
    if include_charts:
        frame.extend(_box(charts, width, title="Utilization"))
    frame.extend(_box(processes, width, title="Processes"))
    if errors:
        frame.append([(f"! {errors[-1]}", "red")])
    frame.append([(HELP_LINE, None)])
    return frame
