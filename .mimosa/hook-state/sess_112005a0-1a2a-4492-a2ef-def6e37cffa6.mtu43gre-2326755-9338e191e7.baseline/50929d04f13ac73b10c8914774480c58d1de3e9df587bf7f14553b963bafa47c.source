"""Deterministic mock backend: full HCUBackend behaviour with no hardware.

Values are pure functions of (seed, device index, per-device call tick), so
tests can assert exact numbers while development still sees the numbers move
between refreshes. ``fail_indices`` makes selected devices raise, exercising
the None/N/A and error-collection paths without hardware.
"""

from __future__ import annotations

from hytop.backends.base import HCUBackend
from hytop.ffi.errors import DeviceNotFoundError, MetricNotSupportedError
from hytop.models.device import DeviceInfo, DeviceMetrics, TemperatureInfo
from hytop.models.process import HcuProcessInfo, ProcessDeviceUsage

MEMORY_TOTAL = 128 * 1024**3  # bytes
SCLK_TABLE = (300.0, 600.0, 800.0, 1000.0, 1150.0, 1200.0, 1250.0, 1300.0)
MCLK_MHZ = 875.0
POWER_CAP_W = 800.0

# (pid, name, pasid, device indices, vram fraction of total, cu occupancy %)
_MOCK_PROCS = (
    (10001, "mocktrain", 20001, (0, 1), 0.35, 95.5),
    (10002, "mockserv", 20002, (3,), 0.15, 60.0),
    (10003, "mockeval", 20003, (0, 4, 5), 0.05, 30.5),
)


class MockBackend(HCUBackend):
    def __init__(
        self,
        device_count: int = 8,
        seed: int = 20260903,
        fail_indices: tuple[int, ...] = (),
    ):
        self._count = device_count
        self._seed = seed
        self._fail = set(fail_indices)
        self._ticks = [0] * device_count
        self._initialized = False

    def init(self) -> None:
        self._initialized = True

    def shutdown(self) -> None:
        self._initialized = False

    def device_count(self) -> int:
        return self._count

    def _check_index(self, index: int) -> None:
        if not 0 <= index < self._count:
            raise DeviceNotFoundError(f"device {index} out of range 0..{self._count - 1}")

    def device_info(self, index: int) -> DeviceInfo:
        self._check_index(index)
        bdf = 0x05 + 0x10 * (index // 4)
        return DeviceInfo(
            index=index,
            name="MOCK DCU-1",
            pci_bus_id=f"0000:{bdf:02x}:00.{index % 4:x}",
            device_id=f"0x{0x6430 + index:x}",
            unique_id=str(1000 + index),
            numa_node=index % 4,
            memory_total=MEMORY_TOTAL,
            cu_count=64,
        )

    def device_metrics(self, index: int) -> DeviceMetrics:
        self._check_index(index)
        if index in self._fail:
            raise MetricNotSupportedError(f"mock: device {index} metrics unavailable")
        tick = self._ticks[index]
        self._ticks[index] += 1

        edge = 30.0 + (7 * index + 5 * tick) % 45
        util = 39.0 + (37 + 11 * index + 13 * tick) % 61
        mem_pct = 55 + (index + 3 * tick) % 40
        return DeviceMetrics(
            index=index,
            utilization=float(util),
            cu_utilization=float((util + 3) % 101),
            memory_used=MEMORY_TOTAL * mem_pct // 100,
            memory_total=MEMORY_TOTAL,
            temperature=TemperatureInfo(
                edge=float(edge),
                junction=edge + 5.0,
                memory=edge + 3.0,
                core=max(0.0, edge - 2.0),
            ),
            power=float(120 + (17 * index + 23 * tick) % 300),
            power_cap=POWER_CAP_W,
            sclk_mhz=SCLK_TABLE[(index + tick) % len(SCLK_TABLE)],
            mclk_mhz=MCLK_MHZ,
        )

    def device_util_window(
        self,
        index: int,
        duration_ms: int,
    ) -> tuple[float | None, float | None]:
        self._check_index(index)
        if index in self._fail:
            raise MetricNotSupportedError(f"mock: device {index} util window unavailable")
        # Deliberately does NOT sleep: keeps tests fast. Real driver blocks.
        tick = self._ticks[index]
        hcu = float((13 * index + 7 * tick) % 100)
        return hcu, min(100.0, hcu + 2.0)

    def processes(self) -> list[HcuProcessInfo]:
        result = []
        for pid, name, pasid, dev_idx, vram_frac, cu_occ in _MOCK_PROCS:
            devices = {}
            for d in dev_idx:
                d = d % self._count  # keep mock usable with small device_count
                devices[d] = ProcessDeviceUsage(
                    device_index=d,
                    vram_used=int(MEMORY_TOTAL * vram_frac),
                    cu_occupancy=cu_occ,
                    sdma_usage=(pid + d) * 1000,
                )
            result.append(
                HcuProcessInfo(pid=pid, name=name, pasid=pasid, devices=devices)
            )
        return result

    def process_info(self, pid: int, device_index: int) -> ProcessDeviceUsage | None:
        self._check_index(device_index)
        for proc in self.processes():
            if proc.pid == pid:
                return proc.devices.get(device_index)
        return None
