import time
import unittest

from hytop.backends.mock import MEMORY_TOTAL, MockBackend
from hytop.ffi.errors import DeviceNotFoundError, MetricNotSupportedError
from hytop.models.device import DeviceInfo


class TestMockBackendBasics(unittest.TestCase):
    def setUp(self):
        self.backend = MockBackend()
        self.backend.init()

    def tearDown(self):
        self.backend.shutdown()

    def test_lifecycle_reinit(self):
        self.backend.shutdown()
        self.backend.init()  # re-init after shutdown must work
        self.assertEqual(self.backend.device_count(), 8)

    def test_default_device_count_is_8(self):
        self.assertEqual(self.backend.device_count(), 8)

    def test_device_info_fields(self):
        info = self.backend.device_info(3)
        self.assertIsInstance(info, DeviceInfo)
        self.assertEqual(info.index, 3)
        self.assertIn("MOCK", info.name)
        self.assertTrue(info.pci_bus_id.startswith("0000:"))
        self.assertEqual(info.numa_node, 3 % 4)
        self.assertEqual(info.memory_total, MEMORY_TOTAL)
        self.assertEqual(info.cu_count, 64)

    def test_index_out_of_range(self):
        for fn in (
            lambda: self.backend.device_info(8),
            lambda: self.backend.device_metrics(-1),
            lambda: self.backend.device_util_window(8, 10),
            lambda: self.backend.process_info(10001, 8),
        ):
            with self.assertRaises(DeviceNotFoundError):
                fn()


class TestMockMetrics(unittest.TestCase):
    def setUp(self):
        self.backend = MockBackend()
        self.backend.init()

    def tearDown(self):
        self.backend.shutdown()

    def test_metric_ranges(self):
        for i in range(8):
            m = self.backend.device_metrics(i)
            for value in (m.utilization, m.cu_utilization):
                self.assertIsNotNone(value)
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 100.0)
            self.assertGreaterEqual(m.memory_used, 0)
            self.assertLessEqual(m.memory_used, m.memory_total)
            self.assertGreater(m.temperature.edge, 0.0)
            self.assertGreater(m.power, 0.0)
            self.assertLessEqual(m.power, m.power_cap)
            self.assertIn(m.sclk_mhz, (300.0, 600.0, 800.0, 1000.0, 1150.0, 1200.0, 1250.0, 1300.0))
            self.assertEqual(m.mclk_mhz, 875.0)

    def test_deterministic_same_seed(self):
        a, b = MockBackend(seed=42), MockBackend(seed=42)
        a.init()
        b.init()
        try:
            self.assertEqual(a.device_metrics(0), b.device_metrics(0))
            self.assertEqual(a.device_info(2), b.device_info(2))
        finally:
            a.shutdown()
            b.shutdown()

    def test_values_move_between_calls(self):
        first = self.backend.device_metrics(0)
        second = self.backend.device_metrics(0)
        self.assertNotEqual(first, second)

    def test_fail_indices_raise_not_supported(self):
        backend = MockBackend(fail_indices=(5,))
        backend.init()
        with self.assertRaises(MetricNotSupportedError):
            backend.device_metrics(5)
        with self.assertRaises(MetricNotSupportedError):
            backend.device_util_window(5, 10)
        backend.device_metrics(4)  # neighbours unaffected

    def test_util_window_is_fast_and_in_range(self):
        start = time.monotonic()
        hcu, cu = self.backend.device_util_window(0, 1000)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 0.1)  # mock must not actually sleep 1s
        self.assertGreaterEqual(hcu, 0.0)
        self.assertLessEqual(hcu, 100.0)
        self.assertGreaterEqual(cu, 0.0)
        self.assertLessEqual(cu, 100.0)


class TestMockProcesses(unittest.TestCase):
    def setUp(self):
        self.backend = MockBackend()
        self.backend.init()

    def tearDown(self):
        self.backend.shutdown()

    def test_process_list_shape(self):
        procs = self.backend.processes()
        self.assertEqual({p.pid for p in procs}, {10001, 10002, 10003})
        train = next(p for p in procs if p.pid == 10001)
        self.assertEqual(train.name, "mocktrain")
        self.assertEqual(train.pasid, 20001)
        self.assertEqual(set(train.devices), {0, 1})  # multi-device single PID

    def test_device_usages_within_bounds(self):
        for proc in self.backend.processes():
            for usage in proc.devices.values():
                self.assertEqual(usage.device_index, usage.device_index)
                self.assertLessEqual(usage.vram_used, MEMORY_TOTAL)
                self.assertGreater(usage.vram_used, 0)
                self.assertGreaterEqual(usage.cu_occupancy, 0.0)
                self.assertLessEqual(usage.cu_occupancy, 100.0)

    def test_process_info_consistent_with_list(self):
        expected = next(
            u for p in self.backend.processes() if p.pid == 10003 for u in p.devices.values() if u.device_index == 4
        )
        got = self.backend.process_info(10003, 4)
        self.assertEqual(got, expected)

    def test_process_info_misses(self):
        self.assertIsNone(self.backend.process_info(10001, 7))  # pid not on device 7
        self.assertIsNone(self.backend.process_info(99999, 0))  # unknown pid

    def test_returned_data_is_a_copy(self):
        first = self.backend.processes()
        first[0].devices[0].vram_used = 1
        second = self.backend.processes()
        self.assertNotEqual(second[0].devices[0].vram_used, 1)

    def test_small_device_count_clips_process_devices(self):
        backend = MockBackend(device_count=2)
        backend.init()
        for proc in backend.processes():
            for idx in proc.devices:
                self.assertLess(idx, 2)
        self.assertEqual(backend.device_count(), 2)


if __name__ == "__main__":
    unittest.main()
