"""hytop command line interface.

    hytop                    live curses TUI (T9)
    hytop --once             one snapshot as plain text
    hytop --json             one snapshot as JSON (T8)
    hytop -d 0,1             restrict to devices 0 and 1
    hytop --backend mock     deterministic simulation without hardware

Exit codes: 0 ok, 2 bad usage / driver missing, 3 other driver errors.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time

import hytop
from hytop.backends.mock import MockBackend
from hytop.backends.native import NativeBackend
from hytop.ffi.errors import DriverNotFoundError, HytopError
from hytop.host.proc import ProcessSampler, host_memory
from hytop.host.process import attach_host_info
from hytop.models.snapshot import SystemSnapshot
from hytop.report import snapshot_to_dict

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DRIVER = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hytop",
        description="nvitop-like monitor for Hygon DCU (HCU) devices (read-only)",
    )
    parser.add_argument(
        "-d", "--device",
        metavar="LIST",
        help='comma-separated device indices, e.g. "0,1,3" (default: all)',
    )
    parser.add_argument(
        "--interval", type=float, default=1.0, metavar="SEC",
        help="refresh interval in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--window-ms", type=int, default=200, metavar="MS",
        help="sampling window for HCU%%/CU%% per device (default: 200)",
    )
    parser.add_argument("--once", action="store_true", help="print one snapshot and exit")
    parser.add_argument("--json", action="store_true", help="print one JSON snapshot and exit")
    parser.add_argument(
        "--backend", choices=("native", "mock"), default="native",
        help="data source: native driver or mock simulation (default: native)",
    )
    parser.add_argument("--version", action="version", version=f"hytop {hytop.__version__}")
    return parser


def parse_device_list(spec: str | None, device_count: int) -> list[int]:
    if not spec:
        return list(range(device_count))
    try:
        indices = [int(part) for part in spec.split(",") if part.strip()]
    except ValueError:
        raise ValueError(f"--device expects comma-separated integers, got {spec!r}") from None
    if not indices:
        return list(range(device_count))
    for i in indices:
        if not 0 <= i < device_count:
            raise ValueError(f"device {i} out of range 0..{device_count - 1}")
    return sorted(set(indices))


def make_backend(name: str):
    if name == "mock":
        return MockBackend()
    return NativeBackend()


def _fmt(value, suffix="", na="N/A", precision=1):
    if value is None:
        return na
    if isinstance(value, float):
        return f"{value:.{precision}f}{suffix}"
    return f"{value}{suffix}"


def _fmt_mem_split(used, total):
    if used is None and total is None:
        return "N/A"
    gib = 1024**3

    def g(v):
        return "N/A" if v is None else f"{v / gib:.1f}G"

    return f"{g(used)}/{g(total)}"


def render_once(snapshot: SystemSnapshot) -> str:
    """Plain-text one-shot table (the numbers the TUI must agree with)."""
    lines = []
    hostname = socket.gethostname()
    metrics = snapshot.devices
    errors = snapshot.errors
    lines.append(
        f"hytop {hytop.__version__}  host: {hostname}  "
        f"devices: {len(metrics)}{f'  errors: {len(errors)}' if errors else ''}"
    )
    header = (
        f"{'HCU':>3}  {'Model':<12} {'Temp':>6} {'Power':>7} {'HCU%':>6} "
        f"{'CU%':>6} {'VRAM':>16} {'SCLK':>6} {'MCLK':>6}"
    )
    lines.append(header)
    for index in sorted(metrics):
        m = metrics[index]
        info = snapshot.device_info.get(index)
        name = (info.name if info and info.name else "?").replace("HYGON ", "")
        lines.append(
            f"{index:>3}  {name:<12} {_fmt(m.temperature.edge, 'C', precision=1):>6} "
            f"{_fmt(m.power, 'W'):>7} {_fmt(m.utilization, '%'):>6} "
            f"{_fmt(m.cu_utilization, '%'):>6} {_fmt_mem_split(m.memory_used, m.memory_total):>16} "
            f"{_fmt(m.sclk_mhz, 'M', precision=0):>6} {_fmt(m.mclk_mhz, 'M', precision=0):>6}"
        )
    processes = snapshot.processes
    if processes:
        lines.append("")
        lines.append(
            f"{'PID':>7}  {'USER':<8} {'DEV':>3} {'VRAM':>9} {'CU%':>5} "
            f"{'CPU%':>6} {'MEM%':>5}  COMMAND"
        )
        for proc in processes:
            for dev_index in sorted(proc.devices):
                usage = proc.devices[dev_index]
                vram = "N/A" if usage.vram_used is None else f"{usage.vram_used / 1024**3:.1f}G"
                cu = "N/A" if usage.cu_occupancy is None else f"{usage.cu_occupancy:.1f}"
                cpu = "N/A" if proc.cpu_percent is None else f"{proc.cpu_percent:.1f}"
                mem = "N/A" if proc.host_memory_percent is None else f"{proc.host_memory_percent:.1f}"
                command = (proc.command or proc.name or "?")[:32]
                lines.append(
                    f"{proc.pid:>7}  {(proc.username or '?'):<8} {dev_index:>3} {vram:>9} "
                    f"{cu:>5} {cpu:>6} {mem:>5}  {command}"
                )
    if snapshot.cpu_percent is not None:
        lines.append("")
        lines.append(
            f"host: cpu {_fmt(snapshot.cpu_percent, '%')}  "
            f"mem {_fmt(snapshot.memory_percent, '%')}"
        )
    if errors:
        lines.append("")
        for err in errors:
            lines.append(f"error: {err}")
    return "\n".join(lines)


def run_once(backend, indices, window_ms, sampler, proc_root="/proc") -> SystemSnapshot:
    """Collect everything for a one-shot SystemSnapshot."""
    infos = {i: backend.device_info(i) for i in indices}
    metrics = {i: backend.device_metrics(i) for i in indices}
    errors = []
    for i in indices:
        try:
            hcu, cu = backend.device_util_window(i, window_ms)
        except HytopError as err:
            errors.append(f"HCU{i} utilization: {err}")
            continue
        metrics[i].utilization = hcu
        metrics[i].cu_utilization = cu
    try:
        processes = backend.processes()
    except HytopError as err:
        processes = []
        errors.append(f"process list: {err}")
    attach_host_info(processes, sampler, warmup_seconds=0.2, proc_root=proc_root)
    host_mem = host_memory(proc_root)
    memory_percent = None
    if host_mem:
        total, available = host_mem
        memory_percent = (total - available) / total * 100.0
    return SystemSnapshot(
        timestamp=time.time(),
        device_info=infos,
        devices=metrics,
        processes=processes,
        cpu_percent=sampler.host_cpu_percent(),
        memory_percent=memory_percent,
        errors=errors,
    )


def main(argv=None, backend_factory=make_backend, stdout=None, stderr=None) -> int:
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.interval <= 0:
        print("hytop: --interval must be positive", file=stderr)
        return EXIT_USAGE

    try:
        backend = backend_factory(args.backend)
        backend.init()
    except DriverNotFoundError as err:
        print(f"hytop: {err}", file=stderr)
        return EXIT_USAGE
    except HytopError as err:
        print(f"hytop: {err}", file=stderr)
        return EXIT_DRIVER

    try:
        device_count = backend.device_count()
        try:
            indices = parse_device_list(args.device, device_count)
        except ValueError as err:
            print(f"hytop: {err}", file=stderr)
            return EXIT_USAGE

        if args.once or args.json:
            sampler = ProcessSampler(root="/proc")
            snapshot = run_once(backend, indices, args.window_ms, sampler)
            if args.json:
                print(json.dumps(snapshot_to_dict(snapshot)), file=stdout)
                return EXIT_OK
            print(render_once(snapshot), file=stdout)
            return EXIT_OK

        print(
            f"hytop {hytop.__version__}: TUI not implemented yet (planned T9); "
            f"try --once",
            file=stdout,
        )
        return EXIT_OK
    finally:
        try:
            backend.shutdown()
        except HytopError:
            pass


if __name__ == "__main__":
    sys.exit(main())
