"""dcutop — an nvitop-like monitor for Hygon DCU (HCU) devices.

Read-only monitoring: device enumeration, live metrics with bars and
history charts, process table, JSON output — plus a small read-only
Python API (see dcutop.api). No control operations.
"""

from __future__ import annotations

from dcutop.api import (
    Device,
    HcuProcess,
    processes,
    shutdown,
    snapshot,
    use_mock,
)
from dcutop.backends.mock import MockBackend
from dcutop.backends.native import NativeBackend
from dcutop.collector import Collector
from dcutop.models.snapshot import SystemSnapshot

__version__ = "0.7.0"

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
