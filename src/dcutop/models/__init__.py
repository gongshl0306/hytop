"""Data models shared by backends, collector, API and UI."""

from __future__ import annotations

from dcutop.models.device import DeviceInfo, DeviceMetrics, TemperatureInfo
from dcutop.models.history import DeviceHistory, HostHistory, RingHistory
from dcutop.models.process import HcuProcessInfo, ProcessDeviceUsage
from dcutop.models.snapshot import SystemSnapshot

__all__ = [
    "DeviceInfo",
    "DeviceMetrics",
    "TemperatureInfo",
    "DeviceHistory",
    "HostHistory",
    "RingHistory",
    "HcuProcessInfo",
    "ProcessDeviceUsage",
    "SystemSnapshot",
]
