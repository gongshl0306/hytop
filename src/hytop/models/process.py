"""Process models.

A single process may use several devices at once, so the model is
``HcuProcessInfo.devices: dict[device_index, ProcessDeviceUsage]`` rather
than a flat PID -> device mapping.

Device-side fields (vram, cu occupancy, sdma) come from the HCU backend;
host-side fields (user, cpu, rss) are filled in from /proc by the host layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProcessDeviceUsage:
    """One process's footprint on one device."""

    device_index: int

    vram_used: int | None = None  # bytes
    cu_occupancy: float | None = None  # percent, 0 ~ 100
    sdma_usage: int | None = None  # microseconds


@dataclass
class HcuProcessInfo:
    pid: int
    name: str | None = None
    pasid: int | None = None

    devices: dict[int, ProcessDeviceUsage] = field(default_factory=dict)

    username: str | None = None
    command: str | None = None

    cpu_percent: float | None = None
    host_memory: int | None = None  # RSS, bytes
    host_memory_percent: float | None = None
