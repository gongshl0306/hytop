"""Data models shared by backends, collector, API and UI."""

from __future__ import annotations

from hytop.models.device import DeviceInfo, DeviceMetrics, TemperatureInfo
from hytop.models.history import DeviceHistory, RingHistory
from hytop.models.process import HcuProcessInfo, ProcessDeviceUsage
from hytop.models.snapshot import SystemSnapshot

__all__ = [
    "DeviceInfo",
    "DeviceMetrics",
    "TemperatureInfo",
    "DeviceHistory",
    "RingHistory",
    "HcuProcessInfo",
    "ProcessDeviceUsage",
    "SystemSnapshot",
]
