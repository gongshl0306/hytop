"""Host-side process and system stats from /proc — the psutil replacement.

All parsers take the procfs root as a parameter so tests can feed fixture
trees instead of the live /proc. CPU% follows top/psutil semantics: process
CPU ticks divided by elapsed wall time (a process on one full core reads
~100, on two cores ~200).
"""

from __future__ import annotations

import os
import pwd
import time
from dataclasses import dataclass

CLK_TCK = os.sysconf("SC_CLK_TCK")
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")


@dataclass(frozen=True)
class ProcSample:
    pid: int
    uid: int
    state: str
    name: str  # comm
    command: str  # cmdline, "" when a kernel thread
    rss_bytes: int
    cpu_ticks: float  # utime + stime
    monotonic: float  # sampling wall time for delta math


def parse_stat_line(text: str) -> tuple[int, str, str, float, float, int]:
    """-> (pid, comm, state, utime, stime, rss_pages).

    comm may contain spaces and parentheses; everything after the LAST ')'
    is positional: rest[0] is field 3 (state), so field N sits at rest[N-3]
    (utime=14, stime=15, rss=24).
    """
    head, _, rest_text = text.rpartition(")")
    pid_str, _, comm = head.partition("(")
    rest = rest_text.split()
    state = rest[0] if rest else "?"
    utime = float(rest[11]) if len(rest) > 11 else 0.0
    stime = float(rest[12]) if len(rest) > 12 else 0.0
    rss_pages = int(rest[21]) if len(rest) > 21 else 0
    return int(pid_str), comm, state, utime, stime, rss_pages


def read_cmdline(root: str, pid: int) -> str | None:
    try:
        with open(os.path.join(root, str(pid), "cmdline"), "rb") as f:
            raw = f.read()
    except OSError:
        return None
    parts = [p.decode(errors="replace") for p in raw.split(b"\0") if p]
    if not parts:
        return ""  # kernel thread: caller falls back to comm
    return " ".join(parts)


def sample_process(root: str, pid: int, now: float | None = None) -> ProcSample | None:
    """One process's /proc snapshot; None when it no longer exists."""
    pid_dir = os.path.join(root, str(pid))
    try:
        uid = os.stat(pid_dir).st_uid
        with open(os.path.join(pid_dir, "stat"), "r") as f:
            stat_text = f.read()
    except (OSError, ValueError):
        return None
    pid_, comm, state, utime, stime, rss_pages = parse_stat_line(stat_text)
    command = read_cmdline(root, pid)
    if command is None:
        return None
    if command == "":
        command = f"[{comm}]"
    return ProcSample(
        pid=pid_,
        uid=uid,
        state=state,
        name=comm,
        command=command,
        rss_bytes=rss_pages * PAGE_SIZE,
        cpu_ticks=utime + stime,
        monotonic=time.monotonic() if now is None else now,
    )


def username_for_uid(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def parse_meminfo(text: str) -> dict[str, int]:
    """'MemTotal:  1000 kB' -> {'MemTotal': 1024000} (kB -> bytes)."""
    result = {}
    for line in text.splitlines():
        key, _, value_part = line.partition(":")
        fields = value_part.split()
        if not fields:
            continue
        try:
            result[key.strip()] = int(fields[0]) * 1024
        except ValueError:
            continue
    return result


def host_memory(root: str) -> tuple[int, int] | None:
    """-> (MemTotal, MemAvailable) in bytes; None if unreadable."""
    try:
        with open(os.path.join(root, "meminfo")) as f:
            info = parse_meminfo(f.read())
    except OSError:
        return None
    total = info.get("MemTotal")
    if total is None:
        return None
    return total, info.get("MemAvailable", 0)


def parse_cpu_total(first_line: str) -> int | None:
    """Sum of all tick counts on the aggregate 'cpu ' line."""
    parts = first_line.split()
    if not parts or parts[0] != "cpu":
        return None
    total = 0
    for token in parts[1:]:
        try:
            total += int(token)
        except ValueError:
            return None
    return total


def cpu_total_ticks(root: str) -> int | None:
    try:
        with open(os.path.join(root, "stat")) as f:
            return parse_cpu_total(f.readline())
    except OSError:
        return None


def proc_cpu_percent(prev: ProcSample | None, now: ProcSample | None) -> float | None:
    """Process CPU% between two samples; None before the second sample."""
    if prev is None or now is None:
        return None
    wall = now.monotonic - prev.monotonic
    if wall <= 0:
        return None
    return max(0.0, (now.cpu_ticks - prev.cpu_ticks) / (wall * CLK_TCK) * 100.0)


def core_count(root: str) -> int:
    """Number of logical CPUs from /proc/stat 'cpuN' lines (container-safe)."""
    count = 0
    try:
        with open(os.path.join(root, "stat")) as f:
            for line in f:
                if line.startswith("cpu") and line[3:4].isdigit():
                    count += 1
    except OSError:
        pass
    return count or os.cpu_count() or 1


def host_cpu_percent(
    prev_total: int | None,
    now_total: int | None,
    wall_seconds: float,
    ncores: int = 1,
) -> float | None:
    """Whole-system CPU% normalized to total capacity (0 ~ 100).

    /proc/stat aggregates ticks across all cores, so the delta is divided
    by ncores; unlike process CPU%, this never exceeds 100.
    """
    if prev_total is None or now_total is None or wall_seconds <= 0 or ncores <= 0:
        return None
    return max(0.0, (now_total - prev_total) / (wall_seconds * CLK_TCK * ncores) * 100.0)


class ProcessSampler:
    """Stateful sampler feeding the per-refresh merge in host/process.py.

    Keeps the previous round's samples so CPU% is available from the second
    refresh on; processes that vanished are dropped silently.
    """

    def __init__(self, root: str = "/proc", clock=time.monotonic, ncores: int | None = None):
        self.root = root
        self._clock = clock
        self._ncores = ncores
        self._prev: dict[int, ProcSample] = {}
        self._prev_cpu_pct: dict[int, float | None] = {}
        self._prev_host_total: int | None = None
        self._prev_host_pct: float | None = None
        self._prev_wall: float | None = None

    def refresh(self, pids: list[int]) -> dict[int, ProcSample]:
        now = self._clock()
        host_total = cpu_total_ticks(self.root)
        if self._ncores is None:
            self._ncores = core_count(self.root)
        samples: dict[int, ProcSample] = {}
        for pid in pids:
            sample = sample_process(self.root, pid, now)
            if sample is not None:
                samples[pid] = sample

        self._prev_cpu_pct = {
            pid: proc_cpu_percent(self._prev.get(pid), sample)
            for pid, sample in samples.items()
        }
        if self._prev_wall is not None and self._prev_host_total is not None:
            self._prev_host_pct = host_cpu_percent(
                self._prev_host_total, host_total, now - self._prev_wall, self._ncores or 1
            )
        else:
            self._prev_host_pct = None
        self._prev = samples
        self._prev_host_total = host_total
        self._prev_wall = now
        return samples

    def cpu_percent(self, pid: int) -> float | None:
        return self._prev_cpu_pct.get(pid)

    def host_cpu_percent(self) -> float | None:
        return self._prev_host_pct
