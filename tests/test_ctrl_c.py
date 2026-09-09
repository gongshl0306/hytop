import io
import unittest
from unittest import mock

from dcutop.backends.mock import MockBackend
from dcutop.cli import main
from dcutop.tui.app import _curses_main
from dcutop.tui.panels import TuiState


class FakeScreen:
    def nodelay(self, flag):
        pass

    def timeout(self, ms):
        pass

    def getch(self):
        raise KeyboardInterrupt


class FakeCollector:
    def __init__(self):
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return None


class TestCtrlC(unittest.TestCase):
    def test_curses_loop_returns_cleanly_on_interrupt(self):
        with mock.patch("curses.curs_set"), \
                mock.patch("dcutop.tui.app.build_attrs", return_value={}):
            screen = FakeScreen()
            collector = FakeCollector()
            # must not raise; returns like the 'q' path
            self.assertIsNone(_curses_main(screen, collector, TuiState(), 0.1))
        self.assertEqual(collector.calls, 1)  # checked once, then exited

    def test_main_returns_130_on_interrupt(self):
        backend = MockBackend()

        def factory(name):
            backend.init()
            return backend

        out, err = io.StringIO(), io.StringIO()
        with mock.patch("dcutop.tui.app.run_tui", side_effect=KeyboardInterrupt):
            code = main(["--backend", "mock"], backend_factory=factory,
                        stdout=out, stderr=err)
        self.assertEqual(code, 130)
        self.assertNotIn("Traceback", out.getvalue() + err.getvalue())
        self.assertFalse(backend._initialized)  # shutdown still ran

    def test_normal_quit_still_exit_zero(self):
        out = io.StringIO()
        with mock.patch("dcutop.tui.app.run_tui", return_value=None):
            code = main(["--backend", "mock"], backend_factory=lambda n: MockBackend(),
                        stdout=out, stderr=io.StringIO())
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
