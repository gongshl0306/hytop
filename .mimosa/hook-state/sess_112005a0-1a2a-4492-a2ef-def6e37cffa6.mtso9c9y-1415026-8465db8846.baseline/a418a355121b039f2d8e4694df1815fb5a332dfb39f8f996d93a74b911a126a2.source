import unittest

from hytop.backends.mock import MockBackend
from hytop.tui.app import _draw
from hytop.tui.panels import TuiState


class FakeStdscr:
    """Records addnstr calls so drawing can be asserted without a pty."""

    def __init__(self, rows, cols):
        self.rows, self.cols = rows, cols
        self.writes = []

    def getmaxyx(self):
        return self.rows, self.cols

    def erase(self):
        self.writes.clear()

    def addnstr(self, y, x, text, n, attr=0):
        self.writes.append((y, x, text[:n], attr))

    def refresh(self):
        pass


def cells_written(screen):
    """Reconstruct (row, column) -> char from the recorded writes."""
    grid = {}
    for y, x, text, _ in screen.writes:
        for offset, ch in enumerate(text):
            grid[(y, x + offset)] = ch
    return grid


class TestDrawClipping(unittest.TestCase):
    def setUp(self):
        import io

        from hytop.tui.app import run_tui

        out = io.StringIO()
        # warm nothing; we only need a snapshot to draw
        self.screen = FakeStdscr(rows=40, cols=80)
        from hytop.collector import Collector

        collector = Collector(MockBackend(), interval=0.05, window_ms=10)
        collector.start()
        try:
            from hytop.tui.app import FIRST_SNAPSHOT_TIMEOUT
            import time

            deadline = time.monotonic() + FIRST_SNAPSHOT_TIMEOUT
            while collector.snapshot() is None:
                if time.monotonic() > deadline:
                    self.fail("no snapshot")
                time.sleep(0.02)
            _draw(self.screen, collector.snapshot(), TuiState(), {}, interval=0.05)
        finally:
            collector.stop()

    def test_right_border_column_is_drawn(self):
        grid = cells_written(self.screen)
        # box borders live in the last column (79); the old width-1 clip
        # skipped them entirely
        rights = [ch for (y, x), ch in grid.items() if x == 79]
        self.assertTrue(rights, "nothing drawn in the last column")
        self.assertIn("│", rights)

    def test_corners_present(self):
        grid = cells_written(self.screen)
        top_left = grid.get((0, 0))
        self.assertEqual(top_left, "┌")
        top_right = grid.get((0, 79))
        self.assertEqual(top_right, "┐")

    def test_border_rows_span_full_width(self):
        grid = cells_written(self.screen)
        top_row = "".join(grid.get((0, x), "?") for x in range(80))
        self.assertEqual(len(top_row), 80)
        self.assertTrue(top_row.startswith("┌"))
        self.assertTrue(top_row.endswith("┐"))
        self.assertNotIn("?", top_row)


if __name__ == "__main__":
    unittest.main()
