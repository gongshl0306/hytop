import dataclasses
import unittest

from hytop.models import (
    DeviceInfo,
    DeviceMetrics,
    HcuProcessInfo,
    ProcessDeviceUsage,
    SystemSnapshot,
    TemperatureInfo,
)


class TestDeviceInfo(unittest.TestCase):
    def test_minimal_construction(self):
        info = DeviceInfo(index=3)
        self.assertEqual(info.index, 3)
        self.assertIsNone(info.name)
        self.assertIsNone(info.pci_bus_id)
        self.assertIsNone(info.device_id)
        self.assertIsNone(info.unique_id)
        self.assertIsNone(info.numa_node)
        self.assertIsNone(info.memory_total)
        self.assertIsNone(info.cu_count)

    def test_frozen(self):
        info = DeviceInfo(index=0)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            info.name = "X"


class TestTemperatureInfo(unittest.TestCase):
    def test_all_sensors_default_none(self):
        t = TemperatureInfo()
        for sensor in ("edge", "junction", "memory", "core"):
            self.assertIsNone(getattr(t, sensor), sensor)

    def test_partial_sensors(self):
        t = TemperatureInfo(edge=58.0)
        self.assertEqual(t.edge, 58.0)
        self.assertIsNone(t.junction)


class TestDeviceMetrics(unittest.TestCase):
    def test_defaults_are_none(self):
        m = DeviceMetrics(index=0)
        for f in (
            "utilization",
            "cu_utilization",
            "memory_used",
            "memory_total",
            "power",
            "power_cap",
            "sclk_mhz",
            "mclk_mhz",
            "pcie_tx_bytes_per_sec",
            "pcie_rx_bytes_per_sec",
        ):
            self.assertIsNone(getattr(m, f), f)

    def test_temperature_defaults_to_empty_info(self):
        m = DeviceMetrics(index=0)
        self.assertIsInstance(m.temperature, TemperatureInfo)
        self.assertIsNone(m.temperature.edge)

    def test_units_documented_values(self):
        # memory in bytes, power in watts, clocks in MHz, util 0-100
        m = DeviceMetrics(
            index=0,
            utilization=96.0,
            cu_utilization=94.0,
            memory_used=58_200_000_000,
            memory_total=64_000_000_000,
            power=412.0,
            power_cap=800.0,
            sclk_mhz=1400.0,
            mclk_mhz=875.0,
        )
        self.assertEqual(m.memory_used, 58_200_000_000)
        self.assertEqual(m.power_cap, 800.0)
        self.assertEqual(m.mclk_mhz, 875.0)

    def test_temperature_info_not_shared_between_instances(self):
        a, b = DeviceMetrics(index=0), DeviceMetrics(index=1)
        a.temperature.edge = 99.0
        self.assertIsNone(b.temperature.edge)


class TestProcessModels(unittest.TestCase):
    def test_minimal_process(self):
        p = HcuProcessInfo(pid=1234)
        self.assertEqual(p.pid, 1234)
        self.assertIsNone(p.name)
        self.assertIsNone(p.pasid)
        self.assertEqual(p.devices, {})
        self.assertIsNone(p.username)
        self.assertIsNone(p.command)
        self.assertIsNone(p.cpu_percent)
        self.assertIsNone(p.host_memory)
        self.assertIsNone(p.host_memory_percent)

    def test_multi_device_same_pid(self):
        # One PID training on several cards: one ProcessDeviceUsage each.
        p = HcuProcessInfo(
            pid=100,
            devices={
                0: ProcessDeviceUsage(device_index=0, vram_used=50 * 2**30, cu_occupancy=96.0),
                1: ProcessDeviceUsage(device_index=1, vram_used=51 * 2**30, cu_occupancy=97.0),
                4: ProcessDeviceUsage(device_index=4, vram_used=32 * 2**30, cu_occupancy=78.0),
            },
        )
        self.assertEqual(sorted(p.devices), [0, 1, 4])
        self.assertEqual(p.devices[1].vram_used, 51 * 2**30)
        self.assertEqual(p.devices[4].cu_occupancy, 78.0)

    def test_process_defaults_not_shared(self):
        a, b = HcuProcessInfo(pid=1), HcuProcessInfo(pid=2)
        a.devices[0] = ProcessDeviceUsage(device_index=0)
        self.assertEqual(b.devices, {})


class TestSystemSnapshot(unittest.TestCase):
    def test_defaults(self):
        import time

        ts = time.time()
        s = SystemSnapshot(timestamp=ts)
        self.assertEqual(s.timestamp, ts)
        self.assertEqual(s.devices, {})
        self.assertEqual(s.processes, [])
        self.assertIsNone(s.cpu_percent)
        self.assertIsNone(s.memory_percent)
        self.assertEqual(s.errors, [])

    def test_mutable_defaults_not_shared(self):
        s1, s2 = SystemSnapshot(timestamp=0.0), SystemSnapshot(timestamp=0.0)
        s1.errors.append("HCU3 temp read failed")
        s1.processes.append(HcuProcessInfo(pid=9))
        self.assertEqual(s2.errors, [])
        self.assertEqual(s2.processes, [])


if __name__ == "__main__":
    unittest.main()
