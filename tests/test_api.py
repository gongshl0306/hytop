import unittest

import dcutop
from dcutop import Collector, Device, MockBackend, snapshot, use_mock
from dcutop.api import _shared_backend, shutdown
from dcutop.ffi.errors import DeviceNotFoundError


class ApiTestBase(unittest.TestCase):
    def setUp(self):
        use_mock()  # every test starts from a fresh deterministic mock

    def tearDown(self):
        use_mock()  # never leak a shutdown backend into other tests


class TestImportSurface(ApiTestBase):
    def test_exports(self):
        for name in ("Device", "HcuProcess", "snapshot", "use_mock",
                     "Collector", "SystemSnapshot", "NativeBackend",
                     "MockBackend", "__version__"):
            self.assertTrue(hasattr(dcutop, name), name)

    def test_import_dcutop_does_not_load_driver(self):
        # importing on a machine without the driver must stay safe
        import dcutop as mod

        self.assertIsInstance(mod.__version__, str)


class TestDevice(ApiTestBase):
    def test_count_and_all(self):
        self.assertEqual(Device.count(), 8)
        devices = Device.all()
        self.assertEqual(len(devices), 8)
        self.assertEqual([d.index for d in devices], list(range(8)))

    def test_index_out_of_range(self):
        with self.assertRaises(DeviceNotFoundError):
            Device(99)

    def test_identity_properties(self):
        dev = Device(0)
        self.assertIn("MOCK", dev.name)
        self.assertTrue(dev.pci_bus_id.startswith("0000:"))
        self.assertEqual(dev.cu_count, 64)
        self.assertEqual(dev.memory_total, 128 * 1024**3)

    def test_metrics_instant(self):
        m = Device(0).metrics()
        self.assertIsNotNone(m.utilization)  # instant busy fallback
        self.assertIsNotNone(m.cu_utilization)  # mock provides one
        self.assertEqual(m.memory_total, 128 * 1024**3)

    def test_snapshot_has_windowed_utilization(self):
        m = Device(0).snapshot(window_ms=10)
        self.assertIsNotNone(m.utilization)
        self.assertIsNotNone(m.cu_utilization)

    def test_instant_metrics_contract(self):
        m = Device(0).metrics()
        self.assertIsNotNone(m.utilization)
        self.assertIsNotNone(m.memory_total)

    def test_human_helpers(self):
        dev = Device(0)
        self.assertRegex(dev.memory_used_human(), r"^[\d.]+[KMGTP]")
        self.assertRegex(dev.memory_total_human(), r"^\d+\.0G$")
        self.assertRegex(dev.memory_free_human(), r"^[\d.]+G$")

    def test_na_when_value_missing(self):
        from dcutop.models.device import DeviceMetrics

        dev = Device(0)
        dev._backend = type("B", (), {
            "device_metrics": lambda self, i: DeviceMetrics(index=i),
            "processes": lambda self: [],
        })()
        self.assertEqual(dev.memory_used_human(), "N/A")
        self.assertEqual(dev.memory_total_human(), "N/A")
        self.assertEqual(dev.memory_free_human(), "N/A")

    def test_temperature_sensors(self):
        dev = Device(0)
        self.assertIsNotNone(dev.temperature())  # default edge
        self.assertIsNotNone(dev.temperature("junction"))

    def test_repr(self):
        self.assertIn("index=0", repr(Device(0)))


class TestProcesses(ApiTestBase):
    def test_all_processes_wrapped(self):
        from dcutop.api import processes

        procs = processes()
        self.assertEqual({p.pid for p in procs}, {10001, 10002, 10003})
        first = procs[0]
        self.assertEqual(first.name, "mocktrain")
        self.assertIsNone(first.username)  # mock pids are not in /proc

    def test_device_processes_filtered(self):
        dev0 = Device(0).processes()
        self.assertEqual({p.pid for p in dev0}, {10001, 10003})
        for proc in dev0:
            self.assertIn(0, proc.devices)

    def test_usage_views_and_human_formatting(self):
        from dcutop.api import processes

        proc = processes()[0]
        usage = proc.devices[0]
        self.assertEqual(usage.device_index, 0)
        self.assertGreater(usage.vram_used, 0)
        self.assertRegex(usage.vram_used_human, r"^[\d.]+G$")
        self.assertEqual(proc.vram_used(0), usage.vram_used)
        self.assertEqual(proc.vram_used_human(7), "N/A")  # not on device 7

    def test_cpu_percent_none_without_proc_entry(self):
        from dcutop.api import processes

        for proc in processes():
            self.assertIsNone(proc.cpu_percent)

    def test_repr(self):
        from dcutop.api import processes

        procs = processes()
        self.assertIn("pid=10001", repr(procs[0]))


class TestSnapshot(ApiTestBase):
    def test_snapshot_shape(self):
        snap = snapshot(window_ms=10)
        self.assertEqual(len(snap.devices), 8)
        self.assertEqual(len(snap.processes), 3)
        self.assertEqual(snap.errors, [])
        dev = snap.devices[0]
        self.assertIsNotNone(dev.utilization)
        self.assertIsNotNone(dev.cu_utilization)
        self.assertIsNotNone(dev.temperature.edge)


class TestSharedBackendLifecycle(ApiTestBase):
    def test_use_mock_switches_and_shuts_old(self):
        import dcutop.api as api_mod

        old = api_mod._shared_backend
        use_mock(device_count=4)
        self.assertIsNot(api_mod._shared_backend, old)
        self.assertEqual(Device.count(), 4)

    def test_shutdown_resets_and_lazy_reinit(self):
        import dcutop.api as api_mod

        shutdown()
        self.assertIsNone(api_mod._shared_backend)
        use_mock()  # re-init via a mock (native would fail without a driver)
        self.assertIsNotNone(api_mod._shared_backend)


class TestCollectorCallback(unittest.TestCase):
    def test_callback_receives_snapshots_and_can_stop(self):
        import time

        seen = []

        def on_collect(snap):
            seen.append(snap)
            return len(seen) < 2  # False on the 2nd -> stop

        collector = Collector(MockBackend(), interval=0.05, window_ms=10,
                              on_collect=on_collect)
        collector.start()
        deadline = time.monotonic() + 5
        while collector._thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(collector._thread.is_alive())  # callback stopped it
        self.assertGreaterEqual(len(seen), 2)
        collector.stop()

    def test_callback_exception_does_not_kill_thread(self):
        import time

        def on_collect(snap):
            raise RuntimeError("callback boom")

        collector = Collector(MockBackend(), interval=0.05, window_ms=10,
                              on_collect=on_collect)
        collector.start()
        deadline = time.monotonic() + 5
        found = False
        while time.monotonic() < deadline:
            snap = collector.snapshot()
            if snap is not None and any("callback boom" in e for e in snap.errors):
                found = True
                break
            time.sleep(0.02)
        self.assertTrue(found)
        self.assertIsNotNone(collector._thread)  # still running
        collector.stop()


if __name__ == "__main__":
    unittest.main()
