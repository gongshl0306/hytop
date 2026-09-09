"""Public Python API — the nvitop-style facade over the backend layers.

Example::

    from dcutop import Device, snapshot

    Device.count()                       # 8
    dev = Device(0)
    dev.name                             # 'HYGON DCU-3G'
    dev.memory_used_human()              # '136.2G'

    m = dev.snapshot()                   # windowed HCU%/CU% + instant metrics
    m.power, m.temperature.edge

    for proc in dev.processes():         # HcuProcess on this device
        print(proc.pid, proc.username, proc.vram_used_human(0))

    snap = snapshot()                    # whole-system SystemSnapshot

The shared backend is initialized lazily on first use and shut down at
exit. ``use_mock()`` swaps in the deterministic simulator so the API
works on machines without HCU hardware. CPU% needs two samples: the
first ``processes()`` call warms the sampler (0.2 s) and returns None.
"""

from __future__ import annotations

import atexit

from dcutop.backends.mock import MockBackend
from dcutop.backends.native import NativeBackend
from dcutop.host.proc import ProcessSampler
from dcutop.host.process import attach_host_info
from dcutop.models.device import DeviceInfo, DeviceMetrics
from dcutop.models.history import HostHistory  # noqa: F401 (re-export convenience)
from dcutop.models.process import HcuProcessInfo, ProcessDeviceUsage
from dcutop.models.snapshot import SystemSnapshot
from dcutop.tui.formatter import NA, fmt_bytes

__all__ = [
    "Device",
    "HcuProcess",
    "processes",
    "snapshot",
    "shutdown",
    "use_mock",
    "SystemSnapshot",
]

_shared_backend: NativeBackend | MockBackend | None = None
_shared_sampler: ProcessSampler | None = None
_sampler_warmed = False


def _shared() -> NativeBackend | MockBackend:
    """Lazily initialized process-wide backend (real driver by default)."""
    global _shared_backend
    if _shared_backend is None:
        _shared_backend = NativeBackend()
        _shared_backend.init()
        atexit.register(shutdown)
    return _shared_backend


def use_mock(**kwargs) -> None:
    """Switch the shared backend to the deterministic simulator.

    Handy for trying the API (and the whole package) on machines without
    HCU hardware. Accepts :class:`~dcutop.backends.mock.MockBackend`
    arguments such as ``device_count`` and ``fail_indices``.
    """
    global _shared_backend
    if _shared_backend is not None:
        try:
            _shared_backend.shutdown()
        except Exception:
            pass
    _shared_backend = MockBackend(**kwargs)
    _shared_backend.init()


def shutdown() -> None:
    """Release the shared backend (called automatically at exit)."""
    global _shared_backend
    if _shared_backend is not None:
        try:
            _shared_backend.shutdown()
        except Exception:
            pass
        _shared_backend = None


class ProcessDeviceUsageView:
    """Attribute access + human formatting for one (process, device) pair."""

    def __init__(self, usage: ProcessDeviceUsage):
        self._usage = usage

    @property
    def device_index(self) -> int:
        return self._usage.device_index

    @property
    def vram_used(self) -> int | None:
        return self._usage.vram_used

    @property
    def vram_used_human(self) -> str:
        return fmt_bytes(self._usage.vram_used)

    @property
    def cu_occupancy(self) -> float | None:
        return self._usage.cu_occupancy

    @property
    def sdma_usage(self) -> int | None:
        return self._usage.sdma_usage

    def __repr__(self) -> str:
        return (f"<ProcessDeviceUsage device={self._usage.device_index} "
                f"vram={self.vram_used_human}>")


class HcuProcess:
    """Read-only view of one process using HCU devices (nvitop Process ≈)."""

    def __init__(self, info: HcuProcessInfo):
        self._info = info

    @property
    def pid(self) -> int:
        return self._info.pid

    @property
    def name(self) -> str | None:
        return self._info.name

    @property
    def username(self) -> str | None:
        return self._info.username

    @property
    def command(self) -> str | None:
        return self._info.command

    @property
    def pasid(self) -> int | None:
        return self._info.pasid

    @property
    def cpu_percent(self) -> float | None:
        return self._info.cpu_percent

    @property
    def host_memory(self) -> int | None:
        return self._info.host_memory

    @property
    def host_memory_percent(self) -> float | None:
        return self._info.host_memory_percent

    @property
    def devices(self) -> dict[int, ProcessDeviceUsageView]:
        return {
            index: ProcessDeviceUsageView(usage)
            for index, usage in self._info.devices.items()
        }

    def vram_used(self, device_index: int) -> int | None:
        usage = self._info.devices.get(device_index)
        return usage.vram_used if usage else None

    def vram_used_human(self, device_index: int) -> str:
        usage = self._info.devices.get(device_index)
        return fmt_bytes(usage.vram_used) if usage else NA

    def __repr__(self) -> str:
        devs = ",".join(str(d) for d in sorted(self._info.devices))
        return f"<HcuProcess pid={self.pid} devices=[{devs}]>"


def _attach_host_fields(infos: list[HcuProcessInfo]) -> None:
    """Fill username/command/CPU%/RSS from /proc (shared sampler)."""
    global _shared_sampler, _sampler_warmed
    if _shared_sampler is None:
        _shared_sampler = ProcessSampler(root="/proc")
    attach_host_info(
        infos,
        _shared_sampler,
        proc_root="/proc",
        warmup_seconds=None if _sampler_warmed else 0.2,
    )
    _sampler_warmed = True


class Device:
    """One HCU device (nvitop Device ≈). Obtain via ``Device(index)`` or
    ``Device.all()`` — the shared backend is initialized automatically."""

    def __init__(self, index: int, *, backend=None):
        self._backend = backend if backend is not None else _shared()
        self.index = index
        self._info: DeviceInfo = self._backend.device_info(index)

    # -- class-level -------------------------------------------------------

    @classmethod
    def count(cls) -> int:
        return _shared().device_count()

    @classmethod
    def all(cls) -> list["Device"]:
        return [cls(index) for index in range(cls.count())]

    # -- static identity ---------------------------------------------------

    @property
    def name(self) -> str | None:
        return self._info.name

    @property
    def pci_bus_id(self) -> str | None:
        return self._info.pci_bus_id

    @property
    def numa_node(self) -> int | None:
        return self._info.numa_node

    @property
    def cu_count(self) -> int | None:
        return self._info.cu_count

    @property
    def memory_total(self) -> int | None:
        return self._info.memory_total

    # -- metrics -----------------------------------------------------------

    def metrics(self) -> DeviceMetrics:
        """Instant metrics (fast; HCU% here is the instant busy ratio)."""
        return self._backend.device_metrics(self.index)

    def snapshot(self, window_ms: int = 150) -> DeviceMetrics:
        """Full metrics including windowed HCU%/CU% (blocks ~2x window_ms)."""
        metrics = self.metrics()
        metrics.utilization, metrics.cu_utilization = \
            self._backend.device_util_window(self.index, window_ms)
        return metrics

    def memory_used(self) -> int | None:
        return self.metrics().memory_used

    def memory_used_human(self) -> str:
        return fmt_bytes(self.metrics().memory_used)

    def memory_free_human(self) -> str:
        m = self.metrics()
        if m.memory_used is None or m.memory_total is None:
            return NA
        return fmt_bytes(m.memory_total - m.memory_used)

    def memory_total_human(self) -> str:
        return fmt_bytes(self.metrics().memory_total)

    def utilization(self) -> float | None:
        """Instant busy percent (fast, no sampling window)."""
        return self.metrics().utilization

    def power(self) -> float | None:
        return self.metrics().power

    def power_cap(self) -> float | None:
        return self.metrics().power_cap

    def temperature(self, sensor: str = "edge") -> float | None:
        return getattr(self.metrics().temperature, sensor, None)

    # -- processes ---------------------------------------------------------

    def processes(self) -> list[HcuProcess]:
        """HCU processes running on THIS device, host fields attached."""
        infos = self._backend.processes()
        _attach_host_fields(infos)
        return [HcuProcess(info) for info in infos
                if self.index in info.devices]

    def __repr__(self) -> str:
        return (f"<Device(index={self.index}, name={self._info.name!r}, "
                f"memory_total={self._info.memory_total})>")


def processes() -> list[HcuProcess]:
    """All HCU processes with host fields attached (every device)."""
    infos = _shared().processes()
    _attach_host_fields(infos)
    return [HcuProcess(info) for info in infos]


def snapshot(window_ms: int = 150) -> SystemSnapshot:
    """Whole-system snapshot (devices + processes + host), nvitop's
    ``take_snapshots()`` ≈. Blocks for about window_ms per device."""
    from dcutop.cli import run_once

    backend = _shared()
    indices = list(range(backend.device_count()))
    return run_once(backend, indices, window_ms, ProcessSampler(root="/proc"),
                    proc_root="/proc")
