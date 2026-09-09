"""Snapshot serialization for `hytop --json`.

The schema is a stable contract for shell scripts, agents and future
exporters: null means "not available", device dict keys are strings (JSON
requires string keys), and all units follow the project contract
(bytes, degrees C, watts, MHz, percent).
"""

from __future__ import annotations

import time

from hytop.models.snapshot import SystemSnapshot


def snapshot_to_dict(snapshot: SystemSnapshot) -> dict:
    devices = []
    for index in sorted(snapshot.devices):
        metric = snapshot.devices[index]
        info = snapshot.device_info.get(index)
        temperature = metric.temperature
        devices.append(
            {
                "index": index,
                "name": info.name if info else None,
                "pci_bus_id": info.pci_bus_id if info else None,
                "numa_node": info.numa_node if info else None,
                "cu_count": info.cu_count if info else None,
                "utilization": metric.utilization,
                "cu_utilization": metric.cu_utilization,
                "memory_used": metric.memory_used,
                "memory_total": metric.memory_total,
                "temperature": {
                    "edge": temperature.edge,
                    "junction": temperature.junction,
                    "memory": temperature.memory,
                    "core": temperature.core,
                },
                "power": metric.power,
                "power_cap": metric.power_cap,
                "sclk_mhz": metric.sclk_mhz,
                "mclk_mhz": metric.mclk_mhz,
            }
        )

    processes = []
    for proc in snapshot.processes:
        processes.append(
            {
                "pid": proc.pid,
                "name": proc.name,
                "username": proc.username,
                "command": proc.command,
                "cpu_percent": proc.cpu_percent,
                "host_memory": proc.host_memory,
                "host_memory_percent": proc.host_memory_percent,
                "devices": {
                    str(dev_index): {
                        "vram_used": usage.vram_used,
                        "cu_occupancy": usage.cu_occupancy,
                        "sdma_usage": usage.sdma_usage,
                    }
                    for dev_index, usage in sorted(proc.devices.items())
                },
            }
        )

    return {
        "hytop_version": _version(),
        "timestamp": snapshot.timestamp,
        "host": {
            "cpu_percent": snapshot.cpu_percent,
            "memory_percent": snapshot.memory_percent,
        },
        "devices": devices,
        "processes": processes,
        "errors": list(snapshot.errors),
    }


def _version() -> str:
    from hytop import __version__

    return __version__
