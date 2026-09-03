import unittest

from hytop.backends.native import NativeBackend
from hytop.ffi.errors import DeviceNotFoundError, DriverInitError, RsmiCallError
from hytop.models.device import DeviceInfo

REAL_TOTAL = 154602045440  # bytes, from the target machine


class FakeRsmi:
    """Mimics the converted-value surface of RsmiApi with injectable faults.

    ``fail`` is a set of capability names; any read hitting a failed
    capability raises RsmiCallError the way the real driver does.
    """

    def __init__(self, fail=()):
        self.fail = set(fail)
        self.inited = False
        self.num_devices_calls = 0

    def _ok(self, key):
        if key in self.fail:
            raise RsmiCallError(2, f"fake: {key} not supported")
        if not self.inited:
            raise RsmiCallError(-1, "fake: not initialized")

    # lifecycle
    def init(self):
        if "init" in self.fail:
            raise DriverInitError("fake: init failed")
        self.inited = True

    def shutdown(self):
        self.inited = False

    # identity
    def num_devices(self):
        self.num_devices_calls += 1
        self._ok("num_devices")
        return 8

    def device_name(self, i):
        self._ok("name")
        return "HYGON DCU-3G"

    def device_id(self, i):
        self._ok("device_id")
        return "0x6430"

    def pci_bus_id(self, i):
        self._ok("pci")
        return f"0000:{0x05 + i:02x}:00.0"

    def numa_node(self, i):
        self._ok("numa")
        return i % 4

    def cu_num(self, i):
        self._ok("cu_num")
        return 64

    def memory_total(self, i):
        self._ok("memory_total")
        return REAL_TOTAL

    # metrics
    def memory_used(self, i):
        self._ok("memory_used")
        return 146208546816

    def busy_percent(self, i):
        self._ok("busy")
        return 37

    def power(self, i):
        self._ok("power")
        return 162.0

    def power_cap(self, i):
        self._ok("power_cap")
        return 800.0

    def temperature(self, i, sensor):
        self._ok(f"temp{sensor}")
        return {0: 31.0, 1: 36.0, 2: 42.0, 11: 30.0}[sensor]

    def clk_mhz(self, i, clk_type):
        self._ok("clk")
        return 1200.0 if clk_type == 0 else 875.0

    def hcu_util(self, i, duration_ms):
        self._ok("hcu_util")
        return 87.5

    def cu_util(self, i, duration_ms):
        self._ok("cu_util")
        return 91.2

    # processes
    def compute_process_pids(self):
        self._ok("proc_pids")
        return [(69132, 32813), (70118, 32808)]

    def compute_process_info_v2(self, pid):
        self._ok("proc_v2")
        if pid == 69132:
            return {"pid": pid, "vram_bytes": 144912814080, "vram_rate": 93.73,
                    "gpus": [(1, 0.0)]}
        return {"pid": pid, "vram_bytes": 144755302400, "vram_rate": 93.63,
                "gpus": [(0, 50.0), (3, 60.0)]}

    def process_info_by_device(self, pid, d):
        self._ok(f"proc_by_dev{d}")
        return {"vram_bytes": 144912814080 if d == 1 else 72000000000,
                "sdma_usage": 42, "cu_occupancy": 12.5}


def make_backend(**kwargs):
    fake = FakeRsmi(**kwargs)
    backend = NativeBackend(rsmi=fake)
    backend.init()
    return backend, fake


class TestLifecycle(unittest.TestCase):
    def test_init_caches_device_count(self):
        backend, fake = make_backend()
        for _ in range(3):
            self.assertEqual(backend.device_count(), 8)
        self.assertEqual(fake.num_devices_calls, 1)

    def test_init_failure_propagates(self):
        backend = NativeBackend(rsmi=FakeRsmi(fail=("init",)))
        with self.assertRaises(DriverInitError):
            backend.init()

    def test_unbound_backend_reports_zero_devices_and_rejects_reads(self):
        backend = NativeBackend()  # no rsmi injected, init never called
        self.assertEqual(backend.device_count(), 0)
        with self.assertRaises(DeviceNotFoundError):
            backend.device_metrics(0)


class TestDeviceInfo(unittest.TestCase):
    def setUp(self):
        self.backend, self.fake = make_backend()

    def test_bounds(self):
        for bad in (8, -1, 100):
            with self.assertRaises(DeviceNotFoundError):
                self.backend.device_info(bad)

    def test_fields_assembled(self):
        info = self.backend.device_info(3)
        self.assertIsInstance(info, DeviceInfo)
        self.assertEqual(info.name, "HYGON DCU-3G")
        self.assertEqual(info.device_id, "0x6430")
        self.assertEqual(info.pci_bus_id, "0000:08:00.0")
        self.assertEqual(info.numa_node, 3)
        self.assertEqual(info.memory_total, REAL_TOTAL)
        self.assertEqual(info.cu_count, 64)

    def test_single_field_failure_degrades_to_none(self):
        self.fake.fail.add("cu_num")
        info = self.backend.device_info(0)
        self.assertIsNone(info.cu_count)
        self.assertEqual(info.name, "HYGON DCU-3G")  # rest intact
        self.assertEqual(info.memory_total, REAL_TOTAL)


class TestDeviceMetrics(unittest.TestCase):
    def setUp(self):
        self.backend, self.fake = make_backend()

    def test_bounds(self):
        with self.assertRaises(DeviceNotFoundError):
            self.backend.device_metrics(8)

    def test_fields_assembled(self):
        m = self.backend.device_metrics(0)
        self.assertEqual(m.index, 0)
        self.assertEqual(m.utilization, 37.0)  # instant busy fallback
        self.assertIsNone(m.cu_utilization)  # window fills this
        self.assertEqual(m.memory_used, 146208546816)
        self.assertEqual(m.memory_total, REAL_TOTAL)
        self.assertEqual(m.temperature.edge, 31.0)
        self.assertEqual(m.temperature.junction, 36.0)
        self.assertEqual(m.temperature.memory, 42.0)
        self.assertEqual(m.temperature.core, 30.0)
        self.assertEqual(m.power, 162.0)
        self.assertEqual(m.power_cap, 800.0)
        self.assertEqual(m.sclk_mhz, 1200.0)
        self.assertEqual(m.mclk_mhz, 875.0)

    def test_partial_failures(self):
        self.fake.fail |= {"memory_used", "temp11", "power_cap"}
        m = self.backend.device_metrics(0)
        self.assertIsNone(m.memory_used)
        self.assertIsNone(m.temperature.core)
        self.assertIsNotNone(m.temperature.edge)
        self.assertIsNone(m.power_cap)
        self.assertEqual(m.power, 162.0)

    def test_window_values(self):
        hcu, cu = self.backend.device_util_window(0, 200)
        self.assertEqual((hcu, cu), (87.5, 91.2))
        with self.assertRaises(DeviceNotFoundError):
            self.backend.device_util_window(8, 10)


class TestProcesses(unittest.TestCase):
    def setUp(self):
        self.backend, self.fake = make_backend()

    def test_pids_and_pasids(self):
        procs = self.backend.processes()
        self.assertEqual([p.pid for p in procs], [69132, 70118])
        self.assertEqual(procs[0].pasid, 32813)

    def test_per_device_usage_from_by_device(self):
        procs = self.backend.processes()
        single = procs[0]
        self.assertEqual(set(single.devices), {1})
        self.assertEqual(single.devices[1].vram_used, 144912814080)
        self.assertEqual(single.devices[1].sdma_usage, 42)
        self.assertEqual(single.devices[1].cu_occupancy, 12.5)
        multi = procs[1]
        self.assertEqual(set(multi.devices), {0, 3})
        self.assertEqual(multi.devices[0].vram_used, 72000000000)
        self.assertEqual(multi.devices[3].vram_used, 72000000000)

    def test_v2_failure_keeps_pid_with_empty_devices(self):
        self.fake.fail.add("proc_v2")
        procs = self.backend.processes()
        self.assertEqual(len(procs), 2)
        self.assertEqual(procs[0].devices, {})
        self.assertEqual(procs[0].pid, 69132)

    def test_by_device_failure_falls_back_to_v2_rate(self):
        self.fake.fail.add("proc_by_dev3")
        procs = self.backend.processes()
        multi = procs[1]
        self.assertIsNone(multi.devices[3].vram_used)
        self.assertEqual(multi.devices[3].cu_occupancy, 60.0)  # v2 rate
        self.assertEqual(multi.devices[0].vram_used, 72000000000)  # unaffected

    def test_pids_enumeration_failure_propagates(self):
        self.fake.fail.add("proc_pids")
        with self.assertRaises(RsmiCallError):
            self.backend.processes()

    def test_process_info_lookup(self):
        usage = self.backend.process_info(70118, 3)
        self.assertEqual(usage.vram_used, 72000000000)
        self.assertIsNone(self.backend.process_info(70118, 1))  # not used by pid
        self.assertIsNone(self.backend.process_info(1, 0))  # unknown pid
        with self.assertRaises(DeviceNotFoundError):
            self.backend.process_info(69132, 8)


if __name__ == "__main__":
    unittest.main()
