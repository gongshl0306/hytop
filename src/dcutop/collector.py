"""Collector: background thread turning a backend into SystemSnapshots.

Two kinds of reads, two policies:

- Instant metrics (memory/power/temp/clock/busy/processes) are cheap, so
  every device is read every tick.
- Windowed HCU%/CU% BLOCK for ~2x window_ms per device (driver samples the
  window synchronously), so only a few devices are measured per tick and
  the collector rotates through the fleet. Snapshots carry each device's
  last measured window value until its next turn.

Everything runs on the collector thread; the UI only ever reads
``snapshot()`` and never blocks on the driver. Failures are recorded in
``SystemSnapshot.errors`` and previously good data is kept (stale but
labelled) instead of crashing.
"""

from __future__ import annotations

import threading
import time

from dcutop.host.proc import ProcessSampler, host_memory
from dcutop.host.process import attach_host_info
from dcutop.models.history import DeviceHistory, HostHistory
from dcutop.models.snapshot import SystemSnapshot


def _restrict_processes(processes: list, indices: list[int]) -> list:
    """Keep only device usages inside `indices`; drop now-empty processes.

    Implements `-d 0,1` for the process table: a scheduler on HCU4 has no
    rows when the user asked to watch HCU0/HCU1 only.
    """
    if not indices:
        return processes
    allowed = set(indices)
    result = []
    for proc in processes:
        kept = {d: u for d, u in proc.devices.items() if d in allowed}
        if kept:
            proc.devices = kept
            result.append(proc)
    return result


class Collector:
    def __init__(
        self,
        backend,
        interval: float = 1.0,
        window_ms: int = 150,
        devices: list[int] | None = None,
        window_devices_per_tick: int = 2,
        proc_root: str = "/proc",
        clock=time.monotonic,
        on_collect=None,
    ):
        """``on_collect``: optional callable invoked with each finished
        snapshot; returning ``False`` stops the collector (nvitop's
        ``collect_in_background`` style)."""
        self._backend = backend
        self._interval = interval
        self._window_ms = window_ms
        self._window_devices_per_tick = max(1, window_devices_per_tick)
        self._proc_root = proc_root
        self._clock = clock
        self._on_collect = on_collect

        self._indices: list[int] = list(devices) if devices else []
        self._rotation_index = 0
        self._window_values: dict[int, tuple[float | None, float | None]] = {}
        self._last_good_metrics: dict = {}
        self._last_good_processes: list = []
        self._static_cache: dict = {}
        self._history: dict[int, DeviceHistory] = {}
        self._host_history = HostHistory()
        self._mem_total: int | None = None

        self._sampler = ProcessSampler(root=proc_root, clock=clock)

        self._lock = threading.Lock()
        self._snapshot: SystemSnapshot | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("collector already started")
        if not self._indices:
            self._indices = list(range(self._backend.device_count()))
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="dcutop-collector", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def snapshot(self) -> SystemSnapshot | None:
        """Latest snapshot (or None before the first tick finished)."""
        with self._lock:
            return self._snapshot

    # -- collection --------------------------------------------------------

    def _run(self) -> None:
        while not self._stop_event.is_set():
            started = self._clock()
            try:
                self._collect_once()
            except Exception as err:  # never let the thread die silently
                self._record_emergency(err)
            if self._on_collect is not None and self._snapshot_ready():
                try:
                    if self._on_collect(self.snapshot()) is False:
                        self._stop_event.set()  # callback requests shutdown
                except Exception as err:
                    self._record_emergency(err)
            elapsed = self._clock() - started
            self._stop_event.wait(max(0.0, self._interval - elapsed))

    def _snapshot_ready(self) -> bool:
        with self._lock:
            return self._snapshot is not None

    def _record_emergency(self, err: Exception) -> None:
        previous = self._snapshot
        with self._lock:
            self._snapshot = SystemSnapshot(
                timestamp=time.time(),
                device_info=previous.device_info if previous else {},
                devices=previous.devices if previous else {},
                processes=previous.processes if previous else [],
                errors=[*(previous.errors if previous else []), f"collector: {err}"],
            )

    def _collect_once(self) -> None:
        errors: list[str] = []
        metrics: dict = {}

        for index in self._indices:
            try:
                metrics[index] = self._backend.device_metrics(index)
            except Exception as err:
                stale = self._last_good_metrics.get(index)
                if stale is not None:
                    metrics[index] = stale
                errors.append(f"HCU{index}: {err}")
        self._last_good_metrics = metrics

        self._rotate_windows(errors)

        # merge last-known window values into the fresh metrics
        for index, metric in metrics.items():
            if index in self._window_values:
                metric.utilization, metric.cu_utilization = self._window_values[index]
            history = self._history.setdefault(index, DeviceHistory())
            history.append(metric.utilization, metric.cu_utilization,
                           metric.memory_used, metric.power)

        processes = self._collect_processes(errors)

        host_cpu = self._sampler.host_cpu_percent()
        host_mem = self._host_memory_percent()
        self._host_history.append(host_cpu, host_mem)

        snapshot = SystemSnapshot(
            timestamp=time.time(),
            device_info=self._static_infos(errors),
            devices=metrics,
            history={index: hist.copy() for index, hist in self._history.items()},
            host_history=self._host_history.copy(),
            processes=processes,
            cpu_percent=host_cpu,
            memory_percent=host_mem,
            errors=errors,
        )
        with self._lock:
            self._snapshot = snapshot

    def _rotate_windows(self, errors: list[str]) -> None:
        if not self._indices:
            return
        for _ in range(self._window_devices_per_tick):
            index = self._indices[self._rotation_index % len(self._indices)]
            self._rotation_index += 1
            try:
                self._window_values[index] = self._backend.device_util_window(
                    index, self._window_ms
                )
            except Exception as err:
                errors.append(f"HCU{index} utilization: {err}")

    def _collect_processes(self, errors: list[str]) -> list:
        try:
            processes = self._backend.processes()
        except Exception as err:
            errors.append(f"process list: {err}")
            processes = self._last_good_processes
        else:
            self._last_good_processes = processes
        processes = _restrict_processes(processes, self._indices)
        attach_host_info(processes, self._sampler, mem_total=self._mem_total,
                         proc_root=self._proc_root)
        return processes

    def _static_infos(self, errors: list[str]) -> dict:
        for index in self._indices:
            if index not in self._static_cache:
                try:
                    self._static_cache[index] = self._backend.device_info(index)
                except Exception as err:
                    errors.append(f"HCU{index} info: {err}")
        return dict(self._static_cache)

    def _host_memory_percent(self) -> float | None:
        host = host_memory(self._proc_root)
        if host is None:
            return None
        total, available = host
        self._mem_total = total
        return (total - available) / total * 100.0
