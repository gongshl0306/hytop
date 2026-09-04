"""Frame rendering as plain line lists — no curses here, fully testable.

``render_frame`` produces every line of one screen; app.py only positions
them. Process rows are one row per (PID, device) pair, sorted per TuiState.
"""

from __future__ import annotations

import curses
import socket
from dataclasses import dataclass, field

import hytop
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

SORT_KEYS = ("pid", "vram", "cu", "cpu")

BLOCKS = "▁▂▃▄▅▆▇█"
BAR_FULL = "█"
BAR_EMPTY = "░"

UTIL_BAR_WIDTH = 11
MEM_BAR_WIDTH = 10

DEVICE_HEADER = (
    f"{'HCU':>3}  {'Model':<10} {'Temp':>6} {'Power':>6} "
    f"{'HCU%':>{UTIL_BAR_WIDTH + 8}} {'CU%':>6} "
    f"{'VRAM':>{MEM_BAR_WIDTH + 14}} {'SCLK':>6} {'MCLK':>6}"
)
PROCESS_HEADER = (
    f"{'PID':>7}  {'USER':<8} {'HCU':>3} {'VRAM':>7} {'CU%':>5} "
    f"{'CPU%':>6} {'MEM%':>5}  COMMAND"
)

HELP_LINE = (
    "q quit | r refresh | up/down select | p sort PID | m sort VRAM | "
    "c sort CU | u sort CPU | 1-9 filter HCU | a all"
)


def handle_key(state: TuiState, key: int, device_count: int) -> str | None:
    """Key state machine; returns 'quit' or None after mutating state.

    Sort keys pick the process-table sort. Digits toggle devices in/out of
    the process filter (None = show all); 'a' clears the filter.
    """
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


@dataclass
class TuiState:
    process_sort: str = "pid"
    filter_devices: set | None = None
    selected: int = 0


def short_model(name: str | None) -> str:
    if not name:
        return NA
    for prefix in ("HYGON ", "MOCK "):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name[:10]


def bar(value: float | None, width: int = UTIL_BAR_WIDTH,
        maximum: float = 100.0) -> str:
    """`[██████░░░░]` utilization bar; dots when the value is unknown."""
    if value is None:
        return f"[{BAR_EMPTY * width}]"
    if maximum <= 0:
        maximum = 100.0
    fraction = min(1.0, max(0.0, value / maximum))
    filled = int(round(fraction * width))
    return f"[{BAR_FULL * filled}{BAR_EMPTY * (width - filled)}]"


def sparkline(values, width: int = 40) -> str:
    """Values as a block-character trend line; None/gaps render lowest."""
    if width <= 0:
        return ""
    sampled = list(values) if len(values) <= width else _downsample(values, width)
    out = []
    for v in sampled:
        if v is None or v < 0:
            level = 0
        else:
            level = min(len(BLOCKS) - 1, int(v / 100.0 * len(BLOCKS)))
        out.append(BLOCKS[level])
    return "".join(out)


def _downsample(values, width: int) -> list:
    bucket_size = len(values) / width
    sampled = []
    for i in range(width):
        start = int(i * bucket_size)
        end = max(start + 1, int((i + 1) * bucket_size))
        bucket = [v for v in values[start:end] if v is not None and v >= 0]
        sampled.append(sum(bucket) / len(bucket) if bucket else None)
    return sampled


def history_lines(snapshot, spark_width: int = 40, per_line: int = 2) -> list[str]:
    """One trend line per device, `per_line` devices per row."""
    devices = sorted(snapshot.history)
    if not devices:
        return []
    label_width = len(f"HCU{max(devices)}:")
    lines = []
    for start in range(0, len(devices), per_line):
        cells = []
        for index in devices[start:start + per_line]:
            series = snapshot.history[index].utilization.values()
            cells.append(f"{f'HCU{index}:':<{label_width}} {sparkline(series, spark_width)}")
        lines.append("  ".join(cells))
    return lines


def device_lines(snapshot) -> list[str]:
    lines = [DEVICE_HEADER]
    for index in sorted(snapshot.devices):
        m = snapshot.devices[index]
        info = snapshot.device_info.get(index)
        model = short_model(info.name if info else None)
        util_cell = f"{bar(m.utilization)} {fmt_percent(m.utilization)}"
        mem_fraction = None
        if m.memory_used is not None and m.memory_total:
            mem_fraction = m.memory_used / m.memory_total * 100.0
        mem_cell = f"{bar(mem_fraction, MEM_BAR_WIDTH)} {fmt_mem_pair(m.memory_used, m.memory_total)}"
        lines.append(
            f"{index:>3}  {model:<10} {fmt_temp(m.temperature.edge):>6} {fmt_power(m.power):>6} "
            f"{util_cell:>19} {fmt_percent(m.cu_utilization):>6} "
            f"{mem_cell:>24} "
            f"{fmt_clock(m.sclk_mhz):>6} {fmt_clock(m.mclk_mhz):>6}"
        )
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


def process_lines(snapshot, state: TuiState, width: int = 120) -> list[str]:
    rows = _sort_processes(snapshot, state)
    if not rows:
        return [PROCESS_HEADER, "  (no HCU processes)"]
    lines = [PROCESS_HEADER]
    for position, (proc, dev_index, usage) in enumerate(rows):
        marker = ">" if position == state.selected else " "
        vram = fmt_bytes(usage.vram_used)
        cu = NA if usage.cu_occupancy is None else f"{usage.cu_occupancy:.1f}"
        cpu = NA if proc.cpu_percent is None else f"{proc.cpu_percent:.1f}"
        mem = NA if proc.host_memory_percent is None else f"{proc.host_memory_percent:.1f}"
        command = truncate(proc.command or proc.name, max(8, width - 50))
        lines.append(
            f"{marker}{proc.pid:>7}  {(proc.username or NA)[:8]:<8} {dev_index:>3} "
            f"{vram:>7} {cu:>5} {cpu:>6} {mem:>5}  {command}"
        )
    return lines


def render_frame(snapshot, state: TuiState, width: int = 120) -> list[str]:
    errors = snapshot.errors
    title = (
        f"hytop {hytop.__version__}  host: {socket.gethostname()}  "
        f"devices: {len(snapshot.devices)}"
        + (f"  errors: {len(errors)}" if errors else "")
    )
    host = ""
    if snapshot.cpu_percent is not None:
        host = (
            f"host cpu {fmt_percent(snapshot.cpu_percent)}  "
            f"mem {fmt_percent(snapshot.memory_percent)}"
        )
    lines = [f"{title}  {host}".rstrip()]
    lines.append("")
    lines.extend(device_lines(snapshot))
    lines.append("")
    lines.extend(history_lines(snapshot))
    if lines[-1] != "":
        lines.append("")
    lines.extend(process_lines(snapshot, state, width=width))
    lines.append("")
    if errors:
        lines.append(f"! {errors[-1]}")
    lines.append(HELP_LINE)
    return lines
