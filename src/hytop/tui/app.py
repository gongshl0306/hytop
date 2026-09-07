"""curses front-end: a thin loop over the pure panel renderers.

``run_tui`` also supports a HEADLESS mode (``frames=N``) that never touches
curses: it renders N collector ticks and prints the last frame, which makes
the full TUI stack testable and verifiable over ssh without a pty.

Styles from theme.py map to curses attributes; terminals without color
support degrade to bold/plain via an empty color map.
"""

from __future__ import annotations

import curses
import sys
import time

from hytop.collector import Collector
from hytop.tui.panels import TuiState, handle_key, render_frame, text_of
from hytop.tui.theme import STYLE_NAMES

FIRST_SNAPSHOT_TIMEOUT = 10.0


def build_attrs() -> dict[str, int]:
    """Style name -> curses attribute; safe to call before initscr fails."""
    attrs: dict[str, int] = {"bold": curses.A_BOLD}
    try:
        curses.start_color()
        curses.use_default_colors()
    except curses.error:
        return attrs
    colors = {
        "red": curses.COLOR_RED,
        "yellow": curses.COLOR_YELLOW,
        "green": curses.COLOR_GREEN,
    }
    for pair_index, (name, fg) in enumerate(colors.items(), start=1):
        try:
            curses.init_pair(pair_index, fg, -1)
            attrs[name] = curses.color_pair(pair_index) | curses.A_BOLD
        except curses.error:
            continue
    return attrs


def run_tui(backend, devices, interval, window_ms, frames=None, stdout=None) -> None:
    collector = Collector(backend, interval=interval, window_ms=window_ms, devices=devices)
    collector.start()
    state = TuiState()
    try:
        if frames is not None:
            _headless(collector, state, frames, stdout, interval)
        else:
            curses.wrapper(_curses_main, collector, state, interval)
    finally:
        collector.stop()


def _headless(collector: Collector, state: TuiState, frames: int, stdout,
              interval: float = 1.0) -> None:
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
    for line in render_frame(last_snapshot, state, interval_s=interval):
        print(text_of(line), file=out)


def _curses_main(stdscr, collector: Collector, state: TuiState,
                 interval: float = 1.0) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(120)
    attrs = build_attrs()

    drawn_timestamp = None
    while True:
        snapshot = collector.snapshot()
        if snapshot is not None and snapshot.timestamp != drawn_timestamp:
            drawn_timestamp = snapshot.timestamp
            _draw(stdscr, snapshot, state, attrs, interval)
        key = stdscr.getch()
        if key == curses.KEY_RESIZE or key == ord("r"):
            if snapshot is not None:
                _draw(stdscr, snapshot, state, attrs, interval)
            continue
        if key != -1:
            if handle_key(state, key, len(snapshot.devices) if snapshot else 0) == "quit":
                return


def _draw(stdscr, snapshot, state: TuiState, attrs: dict[str, int],
          interval: float = 1.0) -> None:
    height, width = stdscr.getmaxyx()
    lines = render_frame(snapshot, state, width=width,
                         interval_s=interval)[: max(0, height - 1)]
    stdscr.erase()
    for y, line in enumerate(lines):
        column = 0
        for text, style in line:
            if column >= width:
                break
            chunk = text[: width - column]
            try:
                stdscr.addnstr(y, column, chunk, len(chunk), attrs.get(style, 0))
            except curses.error:
                pass  # writing the screen's bottom-right cell raises; safe
            column += len(text)
    stdscr.refresh()
