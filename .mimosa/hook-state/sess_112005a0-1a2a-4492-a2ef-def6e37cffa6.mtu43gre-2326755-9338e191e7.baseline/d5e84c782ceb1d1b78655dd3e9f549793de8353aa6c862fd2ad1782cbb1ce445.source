"""hytop — an nvitop-like monitor for Hygon DCU (HCU) devices.

Read-only monitoring: device enumeration, live metrics with bars and
history charts, process table, JSON output — plus a small read-only
Python API (see hytop.api). No control operations.
"""

from __future__ import annotations

from hytop.api import (
    Device,
    HcuProcess,
    processes,
    shutdown,
    snapshot,
    use_mock,
)
from hytop.backends.mock import MockBackend
from hytop.backends.native import NativeBackend
from hytop.collector import Collector
from hytop.models.snapshot import SystemSnapshot

__version__ = "0.6.0"

__all__ = [
    "__version__",
    "Device",
    "HcuProcess",
    "processes",
    "snapshot",
    "shutdown",
    "use_mock",
    "Collector",
    "SystemSnapshot",
    "NativeBackend",
    "MockBackend",
]
