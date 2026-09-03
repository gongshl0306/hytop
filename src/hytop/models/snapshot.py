"""SystemSnapshot: the single object the TUI and CLI consume.

Everything in a snapshot is already collected and converted; rendering must
never touch the backend. Backend failures are recorded in ``errors`` and the
affected fields stay None (rendered as N/A) instead of crashing the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hytop.models.device import DeviceMetrics
from hytop.models.process import HcuProcessInfo


@dataclass
class SystemSnapshot:
    timestamp: float

    devices: dict[int, DeviceMetrics] = field(default_factory=dict)

    processes: list[HcuProcessInfo] = field(default_factory=list)

    cpu_percent: float | None = None
    memory_percent: float | None = None

    errors: list[str] = field(default_factory=list)
