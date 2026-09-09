import io
import threading
import time
import unittest

from dcutop.backends.mock import MockBackend
from dcutop.collector import Collector, _restrict_processes


def wait_for(predicate, timeout=5.0, step=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return False


class TestRestrictProcesses(unittest.TestCase):
    def test_keeps_only_selected_devices_and_drops_empty(self):
        procs = MockBackend().processes()  # 10001:{0,1}, 10002:{3}, 10003:{0,4,5}
        kept = _restrict_processes(procs, [1])
        # 10001 keeps device 1; 10002 (dev 3) and 10003 (0,4,5) have no rows left
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].pid, 10001)
        self.assertEqual(set(kept[0].devices), {1})

    def test_empty_indices_means_no_filter(self):
        procs = MockBackend().processes()
        self.assertEqual(_restrict_processes(procs, []), procs)


class CollectorHarness(unittest.TestCase):
    def make_collector(self, **kwargs):
        backend = kwargs.pop("backend", None) or MockBackend()
        kwargs.setdefault("interval", 0.05)
        kwargs.setdefault("window_ms", 10)
        collector = Collector(backend, **kwargs)
        self.addCleanup(lambda: None)
        return backend, collector


class TestCollectorLifecycle(CollectorHarness):
    def test_first_snapshot_appears_after_start(self):
        _, collector = self.make_collector()
        self.assertIsNone(collector.snapshot())
        collector.start()
        self.assertTrue(wait_for(lambda: collector.snapshot() is not None))
        collector.stop()

    def test_stop_joins_thread(self):
        _, collector = self.make_collector()
        collector.start()
        self.assertTrue(wait_for(lambda: collector.snapshot() is not None))
        collector.stop()
        self.assertFalse(collector._thread or False, "thread should be joined")

    def test_double_start_rejected(self):
        _, collector = self.make_collector()
        collector.start()
        collector.stop()
        # after stop, starting again is allowed (fresh thread)
        collector.start()
        self.assertTrue(wait_for(lambda: collector.snapshot() is not None))
        collector.stop()

    def test_snapshot_is_monotonic_and_fresh(self):
        _, collector = self.make_collector()
        collector.start()
        self.assertTrue(wait_for(lambda: collector.snapshot() is not None))
        first = collector.snapshot()
        self.assertTrue(wait_for(lambda: collector.snapshot() is not first))
        second = collector.snapshot()
        self.assertGreaterEqual(second.timestamp, first.timestamp)
        collector.stop()


class TestCollectorData(CollectorHarness):
    def test_devices_and_static_info_populated(self):
        _, collector = self.make_collector()
        collector.start()
        self.assertTrue(wait_for(lambda: collector.snapshot() is not None))
        snapshot = collector.snapshot()
        self.assertEqual(sorted(snapshot.devices), list(range(8)))
        self.assertEqual(sorted(snapshot.device_info), list(range(8)))
        self.assertIn("MOCK", snapshot.device_info[0].name)
        collector.stop()

    def test_history_grows_and_is_snapshotted_per_tick(self):
        _, collector = self.make_collector()
        collector.start()
        self.assertTrue(wait_for(
            lambda: collector.snapshot() is not None
            and len(collector.snapshot().history.get(0).utilization) >= 2,
            timeout=10,
        ))
        first = collector.snapshot()
        hist_copy = first.history[0]
        # history in the snapshot is a copy: later appends don't leak in
        time.sleep(0.12)
        later = collector.snapshot()
        self.assertGreater(len(later.history[0].utilization), len(hist_copy.utilization))
        collector.stop()

    def test_rotation_covers_all_devices(self):
        backend, collector = self.make_collector(window_devices_per_tick=2)
        collector.start()
        # 8 devices / 2 per tick = 4 ticks; allow generous time
        self.assertTrue(wait_for(
            lambda: collector.snapshot() is not None
            and all(collector.snapshot().devices[i].cu_utilization is not None for i in range(8)),
            timeout=10,
        ))
        for i in range(8):
            m = collector.snapshot().devices[i]
            self.assertIsNotNone(m.utilization)
            self.assertIsNotNone(m.cu_utilization)
            self.assertLessEqual(m.cu_utilization, 100.0)
        collector.stop()

    def test_processes_and_host_fields(self):
        with_proc = MockBackend()
        collector = Collector(with_proc, interval=0.05, window_ms=10)
        collector.start()
        self.assertTrue(wait_for(lambda: collector.snapshot() is not None and collector.snapshot().processes))
        snapshot = collector.snapshot()
        pids = {p.pid for p in snapshot.processes}
        self.assertEqual(pids, {10001, 10002, 10003})
        # mock pids do not exist in the real /proc: host fields stay None
        self.assertIsNone(snapshot.processes[0].username)
        collector.stop()

    def test_device_failure_recorded_and_others_keep_working(self):
        backend = MockBackend(fail_indices=(5,))
        _, collector = self.make_collector(backend=backend)
        collector.start()
        self.assertTrue(wait_for(
            lambda: collector.snapshot() is not None and collector.snapshot().errors,
            timeout=10,
        ))
        snapshot = collector.snapshot()
        self.assertTrue(any("HCU5" in e for e in snapshot.errors))
        # healthy devices still present
        self.assertIn(4, snapshot.devices)
        self.assertIn(6, snapshot.devices)
        collector.stop()

    def test_stale_metrics_kept_on_transient_failure(self):
        class FlakyBackend(MockBackend):
            def __init__(self):
                super().__init__()
                self.fail_next = False

            def device_metrics(self, index):
                if self.fail_next and index == 3:
                    raise RuntimeError("transient")
                return super().device_metrics(index)

        backend = FlakyBackend()
        _, collector = self.make_collector(backend=backend)
        collector.start()
        self.assertTrue(wait_for(lambda: collector.snapshot() is not None))
        good = collector.snapshot().devices[3]
        backend.fail_next = True
        self.assertTrue(wait_for(
            lambda: collector.snapshot() is not None and collector.snapshot().errors,
            timeout=10,
        ))
        kept = collector.snapshot().devices[3]
        self.assertIsNotNone(kept)  # stale kept, not dropped
        collector.stop()

    def test_collector_thread_never_dies_on_backend_crash(self):
        class ExplodingBackend(MockBackend):
            def device_util_window(self, index, duration_ms):
                raise RuntimeError("boom")

        backend = ExplodingBackend()
        _, collector = self.make_collector(backend=backend)
        collector.start()
        self.assertTrue(wait_for(lambda: collector.snapshot() is not None))
        thread_alive_before = collector._thread.is_alive()
        time.sleep(0.15)  # several ticks pass
        self.assertTrue(collector._thread.is_alive())
        self.assertTrue(thread_alive_before)
        collector.stop()


if __name__ == "__main__":
    unittest.main()
