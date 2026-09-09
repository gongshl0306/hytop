"""Static identity and live metric models for one HCU device.

Unit contract for the whole project (backends must convert, UI must not):

    utilization / cu_utilization   percent, 0 ~ 100
    memory_*                       bytes
    temperature                    degrees Celsius
    power / power_cap              watts
    sclk / mclk                    MHz

``None`` always means "not available on this driver/device" — never 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DeviceInfo:
    """Static identity of a device: read once at startup, never refreshed."""

    index: int

    name: str | None = None
    pci_bus_id: str | None = None
    device_id: str | None = None
    unique_id: str | None = None

    numa_node: int | None = None

    memory_total: int | None = None  # bytes

    cu_count: int | None = None


@dataclass
class TemperatureInfo:
    """Sensor readings in degrees Celsius; None when a sensor is absent."""

    edge: float | None = None
    junction: float | None = None
    memory: float | None = None
    core: float | None = None


@dataclass
class DeviceMetrics:
    """Live metrics for one device at (roughly) one point in time."""

    index: int

    utilization: float | None = None  # HCU busy percent, 0 ~ 100
    cu_utilization: float | None = None  # average CU occupancy, 0 ~ 100

    memory_used: int | None = None  # bytes
    memory_total: int | None = None  # bytes

    temperature: TemperatureInfo = field(default_factory=TemperatureInfo)

    power: float | None = None  # watts
    power_cap: float | None = None  # watts

    sclk_mhz: float | None = None
    mclk_mhz: float | None = None

    pcie_tx_bytes_per_sec: float | None = None
    pcie_rx_bytes_per_sec: float | None = None
