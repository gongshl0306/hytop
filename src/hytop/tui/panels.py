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

DEVICE_HEADER = (
    f"{'HCU':>3}  {'Model':<10} {'Temp':>6} {'Power':>6} {'HCU%':>6} "
    f"{'CU%':>6} {'VRAM':>13} {'SCLK':>6} {'MCLK':>6}"
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


def device_lines(snapshot) -> list[str]:
    lines = [DEVICE_HEADER]
    for index in sorted(snapshot.devices):
        m = snapshot.devices[index]
        lines.append(
            f"{index:>3}  {short_model(snapshot.device_info.get(index).name if snapshot.device_info.get(index) else None):<10} "
            f"{fmt_temp(m.temperature.edge):>6} {fmt_power(m.power):>6} "
            f"{fmt_percent(m.utilization):>6} {fmt_percent(m.cu_utilization):>6} "
            f"{fmt_mem_pair(m.memory_used, m.memory_total):>13} "
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
    lines.extend(process_lines(snapshot, state, width=width))
    lines.append("")
    if errors:
        lines.append(f"! {errors[-1]}")
    lines.append(HELP_LINE)
    return lines
