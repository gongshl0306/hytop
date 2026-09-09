"""Per-device time-series history for the TUI sparklines.

The collector appends the values it displays each tick; snapshots carry a
copy so rendering never races the appends. All stored values share the
project contract (percent 0-100 for utilization, bytes for memory, watts
for power); None stays None and renders as an empty level.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_MAXLEN = 180  # 3 minutes at a 1s tick


class RingHistory:
    """Bounded value series with width-aware downsampling."""

    def __init__(self, maxlen: int = DEFAULT_MAXLEN):
        self.maxlen = maxlen
        self._values: list[float | None] = []

    def append(self, value: float | None) -> None:
        self._values.append(value)
        if len(self._values) > self.maxlen:
            del self._values[: len(self._values) - self.maxlen]

    def values(self) -> tuple[float | None, ...]:
        return tuple(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def sample(self, width: int) -> list[float | None]:
        """Downsample to `width` points by averaging full buckets.

        Fewer points than width -> returned as-is. None entries are kept
        (they lower their bucket's average only if the bucket holds any
        real value; an all-None bucket stays None).
        """
        if width <= 0:
            return []
        values = self._values
        if len(values) <= width:
            return list(values)
        bucket_size = len(values) / width
        sampled: list[float | None] = []
        for i in range(width):
            start = int(i * bucket_size)
            end = max(start + 1, int((i + 1) * bucket_size))
            bucket = [v for v in values[start:end] if v is not None]
            sampled.append(sum(bucket) / len(bucket) if bucket else None)
        return sampled

    def copy(self) -> "RingHistory":
        clone = RingHistory(self.maxlen)
        clone._values = list(self._values)
        return clone


@dataclass
class HostHistory:
    """Host-wide CPU / memory percent series for the charts."""

    cpu_percent: RingHistory = field(default_factory=RingHistory)
    memory_percent: RingHistory = field(default_factory=RingHistory)

    def append(self, cpu_percent: float | None, memory_percent: float | None) -> None:
        self.cpu_percent.append(cpu_percent)
        self.memory_percent.append(memory_percent)

    def copy(self) -> "HostHistory":
        return HostHistory(
            cpu_percent=self.cpu_percent.copy(),
            memory_percent=self.memory_percent.copy(),
        )


@dataclass
class DeviceHistory:
    """The four series the TUI charts for one device."""

    utilization: RingHistory = field(default_factory=RingHistory)
    cu_utilization: RingHistory = field(default_factory=RingHistory)
    memory_used: RingHistory = field(default_factory=RingHistory)
    power: RingHistory = field(default_factory=RingHistory)

    def append(
        self,
        utilization: float | None,
        cu_utilization: float | None,
        memory_used: int | None,
        power: float | None,
    ) -> None:
        self.utilization.append(utilization)
        self.cu_utilization.append(cu_utilization)
        self.memory_used.append(memory_used)
        self.power.append(power)

    def copy(self) -> "DeviceHistory":
        clone = DeviceHistory(
            utilization=self.utilization.copy(),
            cu_utilization=self.cu_utilization.copy(),
            memory_used=self.memory_used.copy(),
            power=self.power.copy(),
        )
        return clone


@dataclass
class HostHistory:
    """Host-wide CPU / memory percent series for the charts."""

    cpu_percent: RingHistory = field(default_factory=RingHistory)
    memory_percent: RingHistory = field(default_factory=RingHistory)

    def append(self, cpu_percent: float | None, memory_percent: float | None) -> None:
        self.cpu_percent.append(cpu_percent)
        self.memory_percent.append(memory_percent)

    def copy(self) -> "HostHistory":
        return HostHistory(
            cpu_percent=self.cpu_percent.copy(),
            memory_percent=self.memory_percent.copy(),
        )
