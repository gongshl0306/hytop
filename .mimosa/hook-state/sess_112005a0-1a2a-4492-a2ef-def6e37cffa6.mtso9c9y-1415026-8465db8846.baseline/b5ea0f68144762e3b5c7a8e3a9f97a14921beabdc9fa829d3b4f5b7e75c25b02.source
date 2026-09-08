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


CPU_FIELD_NAMES = ("user", "nice", "system", "idle", "iowait",
                   "irq", "softirq", "steal", "guest", "guest_nice")
# top's busy definition: idle/iowait/steal are not the CPU working for us,
# and guest is already counted inside user (summing it double counts)
CPU_BUSY_FIELDS = ("user", "nice", "system", "irq", "softirq")


def parse_cpu_fields(line: str) -> dict[str, int] | None:
    """Aggregate 'cpu ' line -> named tick fields; None if not the agg line."""
    parts = line.split()
    if not parts or parts[0] != "cpu":
        return None
    fields: dict[str, int] = {}
    for name, token in zip(CPU_FIELD_NAMES, parts[1:]):
        fields[name] = int(token)
    return fields


def cpu_fields(root: str) -> dict[str, int] | None:
    try:
        with open(os.path.join(root, "stat")) as f:
            return parse_cpu_fields(f.readline())
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
    prev: dict[str, int] | None,
    now: dict[str, int] | None,
    wall_seconds: float,
    ncores: int = 1,
) -> float | None:
    """Whole-system CPU% across ALL cores, normalized to 0 ~ 100.

    /proc/stat aggregates ticks over every core, so the busy delta is
    divided by ncores. Busy follows `top`: user+nice+system+irq+softirq;
    idle and iowait are excluded, steal is not our CPU working, and guest
    is already inside user.
    """
    if not prev or not now or wall_seconds <= 0 or ncores <= 0:
        return None
    busy = sum(now[f] - prev[f] for f in CPU_BUSY_FIELDS)
    return max(0.0, busy / (wall_seconds * CLK_TCK * ncores) * 100.0)


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
        self._prev_host_fields: dict[str, int] | None = None
        self._prev_host_pct: float | None = None
        self._prev_wall: float | None = None

    def refresh(self, pids: list[int]) -> dict[int, ProcSample]:
        now = self._clock()
        host_fields = cpu_fields(self.root)
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
        if self._prev_wall is not None and self._prev_host_fields is not None:
            self._prev_host_pct = host_cpu_percent(
                self._prev_host_fields, host_fields, now - self._prev_wall,
                self._ncores or 1,
            )
        else:
            self._prev_host_pct = None
        self._prev = samples
        self._prev_host_fields = host_fields
        self._prev_wall = now
        return samples

    def cpu_percent(self, pid: int) -> float | None:
        return self._prev_cpu_pct.get(pid)

    def host_cpu_percent(self) -> float | None:
        return self._prev_host_pct
