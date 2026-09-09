"""SystemSnapshot: the single object the TUI and CLI consume.

Everything in a snapshot is already collected and converted; rendering must
never touch the backend. Backend failures are recorded in ``errors`` and the
affected fields stay None (rendered as N/A) instead of crashing the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dcutop.models.device import DeviceInfo, DeviceMetrics
from dcutop.models.history import DeviceHistory, HostHistory
from dcutop.models.process import HcuProcessInfo


@dataclass
class SystemSnapshot:
    timestamp: float

    # static identity per device, read once at startup
    device_info: dict[int, DeviceInfo] = field(default_factory=dict)

    # live metrics per device
    devices: dict[int, DeviceMetrics] = field(default_factory=dict)

    # per-device time series (copies; safe to render while collecting)
    history: dict[int, DeviceHistory] = field(default_factory=dict)

    # host-wide time series
    host_history: HostHistory = field(default_factory=HostHistory)

    processes: list[HcuProcessInfo] = field(default_factory=list)

    cpu_percent: float | None = None
    memory_percent: float | None = None

    errors: list[str] = field(default_factory=list)
