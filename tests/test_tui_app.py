import io
import unittest

import hytop
from hytop.backends.mock import MockBackend
from hytop.tui.app import run_tui


class TestHeadlessTui(unittest.TestCase):
    def test_frames_renders_full_stack(self):
        out = io.StringIO()
        run_tui(
            MockBackend(), None, interval=0.05, window_ms=10, frames=2, stdout=out
        )
        frame = out.getvalue()
        self.assertIn(f"hytop {hytop.__version__}", frame)
        self.assertIn("DCU-1", frame)  # device rows (MOCK prefix stripped)
        self.assertIn("q quit", frame)  # footer
        self.assertIn("mocktrain", frame)  # process rows
        # process pids present
        for pid in ("10001", "10002", "10003"):
            self.assertIn(pid, frame)

    def test_frames_zero_devices_guard(self):
        # device filter path: only device 3, no crash
        out = io.StringIO()
        run_tui(MockBackend(), [3], interval=0.05, window_ms=10, frames=1, stdout=out)
        self.assertIn("DCU-1", out.getvalue())
        self.assertIn("devices: 1", out.getvalue())


if __name__ == "__main__":
    unittest.main()
