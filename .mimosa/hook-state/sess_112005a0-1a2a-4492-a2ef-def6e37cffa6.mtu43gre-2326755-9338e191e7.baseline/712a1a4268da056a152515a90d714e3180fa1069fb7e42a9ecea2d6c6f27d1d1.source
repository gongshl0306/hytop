"""Merge device-side process info (backend) with host-side info (/proc).

The backend knows which processes use which devices and their VRAM; /proc
knows the user, the command line, RSS and CPU%. This module glues the two
by PID and fills HcuProcessInfo host fields in place.
"""

from __future__ import annotations

import time

from hytop.host.proc import ProcessSampler, host_memory, username_for_uid
from hytop.models.process import HcuProcessInfo

DEFAULT_PROC_ROOT = "/proc"


def attach_host_info(
    procs: list[HcuProcessInfo],
    sampler: ProcessSampler,
    mem_total: int | None = None,
    warmup_seconds: float | None = None,
    proc_root: str = DEFAULT_PROC_ROOT,
) -> list[HcuProcessInfo]:
    """Fill username/command/cpu_percent/host_memory on each process.

    CPU% needs a previous sample. One-shot callers (``hytop --once``) pass
    ``warmup_seconds`` to take two refreshes back to back; the long-running
    collector instead keeps one sampler across ticks and passes None.

    Processes that exited between the backend listing and the /proc read
    keep their device info and get no host fields (displayed as-is).
    """
    pids = [p.pid for p in procs]
    if warmup_seconds:
        sampler.refresh(pids)
        time.sleep(warmup_seconds)
    samples = sampler.refresh(pids)

    if mem_total is None:
        host = host_memory(proc_root)
        mem_total = host[0] if host else None

    for proc in procs:
        sample = samples.get(proc.pid)
        if sample is None:
            continue
        proc.name = sample.name
        proc.username = username_for_uid(sample.uid)
        proc.command = sample.command
        proc.host_memory = sample.rss_bytes
        if mem_total:
            proc.host_memory_percent = sample.rss_bytes / mem_total * 100.0
        proc.cpu_percent = sampler.cpu_percent(proc.pid)
    return procs
