"""Backend abstraction: the only hardware-access interface in dcutop.

The UI, collector and public API talk to an HCUBackend; they never see
ctypes, librocm_smi64 or libhydmi. Implementations:

    NativeBackend  ctypes -> /opt/hyhal/lib/librocm_smi64.so   (T5)
    MockBackend    deterministic simulation, no hardware       (this module's
                   sibling, for development and tests)
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from dcutop.models.device import DeviceInfo, DeviceMetrics
from dcutop.models.process import HcuProcessInfo, ProcessDeviceUsage


class HCUBackend(ABC):
    """Read-only monitoring interface. v0.1 has no control operations."""

    @abstractmethod
    def init(self) -> None:
        """Acquire the driver. Call once before any other method."""

    @abstractmethod
    def shutdown(self) -> None:
        """Release the driver. Other methods must not be called afterwards."""

    @abstractmethod
    def device_count(self) -> int:
        """Number of devices visible to the driver."""

    @abstractmethod
    def device_info(self, index: int) -> DeviceInfo:
        """Static identity of one device; cheap to call repeatedly."""

    @abstractmethod
    def device_metrics(self, index: int) -> DeviceMetrics:
        """Instantaneous metrics for one device.

        Must return quickly (well under one refresh interval for the whole
        fleet). Utilization fields may be None even on success; windowed
        utilization belongs to device_util_window.
        """

    @abstractmethod
    def device_util_window(
        self,
        index: int,
        duration_ms: int,
    ) -> tuple[float | None, float | None]:
        """Measure (hcu_util, cu_util) over a time window, in percent.

        This call BLOCKS for roughly duration_ms (the driver samples the
        window synchronously), so it must never run on the UI thread. With
        the real driver, measuring 8 devices serially at 1000ms costs 8s;
        the collector rotates devices instead and keeps the last known
        value per device.
        """

    @abstractmethod
    def processes(self) -> list[HcuProcessInfo]:
        """Device-side view of all GPU processes.

        Only pid/pasid/name/devices are populated here; username, command
        and host CPU/memory are filled in by dcutop.host from /proc.
        """

    @abstractmethod
    def process_info(self, pid: int, device_index: int) -> ProcessDeviceUsage | None:
        """One process's usage on one device; None if it does not use it."""
