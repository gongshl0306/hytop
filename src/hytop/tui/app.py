"""curses front-end: a thin loop over the pure panel renderers.

``run_tui`` also supports a HEADLESS mode (``frames=N``) that never touches
curses: it renders N collector ticks and prints the last frame, which makes
the full TUI stack testable and verifiable over ssh without a pty.
"""

from __future__ import annotations

import curses
import sys
import time

from hytop.collector import Collector
from hytop.tui.panels import TuiState, handle_key, render_frame

FIRST_SNAPSHOT_TIMEOUT = 10.0


def run_tui(backend, devices, interval, window_ms, frames=None, stdout=None) -> None:
    collector = Collector(backend, interval=interval, window_ms=window_ms, devices=devices)
    collector.start()
    state = TuiState()
    try:
        if frames is not None:
            _headless(collector, state, frames, stdout)
        else:
            curses.wrapper(_curses_main, collector, state)
    finally:
        collector.stop()


def _headless(collector: Collector, state: TuiState, frames: int, stdout) -> None:
    out = stdout if stdout is not None else sys.stdout
    deadline = time.monotonic() + FIRST_SNAPSHOT_TIMEOUT
    while collector.snapshot() is None:
        if time.monotonic() > deadline:
            print("hytop: collector produced no snapshot in time", file=sys.stderr)
            return
        time.sleep(0.02)

    seen, last_snapshot = 0, None
    previous_timestamp = None
    while seen < frames:
        snapshot = collector.snapshot()
        if snapshot is not None and snapshot.timestamp != previous_timestamp:
            previous_timestamp = snapshot.timestamp
            last_snapshot = snapshot
            seen += 1
        time.sleep(0.02)
    for line in render_frame(last_snapshot, state):
        print(line, file=out)


def _curses_main(stdscr, collector: Collector, state: TuiState) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(120)

    drawn_timestamp = None
    while True:
        snapshot = collector.snapshot()
        if snapshot is not None and snapshot.timestamp != drawn_timestamp:
            drawn_timestamp = snapshot.timestamp
            _draw(stdscr, snapshot, state)
        key = stdscr.getch()
        if key == curses.KEY_RESIZE or key == ord("r"):
            if snapshot is not None:
                _draw(stdscr, snapshot, state)
            continue
        if key != -1:
            if handle_key(state, key, len(snapshot.devices) if snapshot else 0) == "quit":
                return


def _draw(stdscr, snapshot, state: TuiState) -> None:
    height, width = stdscr.getmaxyx()
    lines = render_frame(snapshot, state, width=width)[: max(0, height - 1)]
    stdscr.erase()
    for y, line in enumerate(lines):
        try:
            stdscr.addnstr(y, 0, line, max(0, width - 1), curses.A_BOLD if y == 0 else 0)
        except curses.error:
            pass  # writing the screen's last cell raises; safe to ignore
    stdscr.refresh()
