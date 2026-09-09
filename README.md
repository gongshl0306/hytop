# dcutop

[![version](https://img.shields.io/badge/version-0.5.2-blue)](#requirements)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![python](https://img.shields.io/badge/python-3.7%2B-blue)](https://www.python.org/)
[![platform](https://img.shields.io/badge/platform-Linux-lightgrey)](#requirements)
[![deps](https://img.shields.io/badge/dependencies-0-success)](#requirements)

**[English](README.md) | [简体中文](README.zh-CN.md)**

An **nvitop-style terminal monitor for Hygon DCU (HCU) accelerators** —
read-only, zero third-party dependencies, with live utilization bars,
braille history charts, a process table, and JSON output.

dcutop talks to the HCU driver the same way `hy-smi` does — through the
standard `rsmi_*` interface of `librocm_smi64.so` via `ctypes` — but turns
it into an interactive, top-like view: device panel, host & GPU utilization
waveforms, per-device process table, threshold coloring, and a stable JSON
schema for scripts and agents.

> Verified on 8× HYGON DCU-3G (BW1100-class, `librocm_smi64.so.2.8`):
> device metrics match `hy-smi` under real inference load — per-card power
> 150 → 400 W, SCLK boost 1200 → 1350 MHz, CU occupancy 55–85%.

## Demo

![dcutop TUI — HYGON DCU-3G under inference load](docs/images/tui.png)

<details>
<summary>Character-cell preview</summary>

```
┌──────────────────────────────────────────────────────────────────────────┐
│ dcutop 0.5.2  host: dcu-node01  devices: 8  Sep 07 07:53:54             │
└──────────────────────────────────────────────────────────────────────────┘
┌─ Devices ────────────────────────────────────────────────────────────────┐
│ HCU  Model     Temp   Power  HCU%                             CU%  VRAM  │
├──────────────────────────────────────────────────────────────────────────┤
│  0  DCU-3G    44.0C   323W  ▏████████████  100.0%  67.2%  ▏███ 137.4/144G │
├──────────────────────────────────────────────────────────────────────────┤
│  1  DCU-3G    44.0C   298W  ▏████████████   99.3%  73.6%  ▏███ 135.6/144G │
└──────────────────────────────────────────────────────────────────────────┘
┌─ Utilization ────────────────────────────────────────────────────────────┐
│ CPU: 2.4%                            AVG GPU UTL: 94.4%                  │
│ ⠋⠋⠋⠋⠋⠋⠋⠋⠋⠋ (last 80s)            ⣽⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿                 │
│ MEM: 8.2%                            AVG GPU MEM: 94.3%                  │
│ ⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀                        ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿                 │
│                |60s        |30s      (time axis, right edge = now)       │
└──────────────────────────────────────────────────────────────────────────┘
┌─ Processes ──────────────────────────────────────────────────────────────┐
│   PID  USER     HCU  VRAM    CU%   CPU%  MEM%  COMMAND                   │
│ 69131  root       0  135.6G  0.0   99.0   0.9  sglang::scheduler_TP0     │
│ 69132  root       1  135.6G  0.0   97.3   0.9  sglang::scheduler_TP1     │
└──────────────────────────────────────────────────────────────────────────┘
q quit | r refresh | up/down select | p sort PID | m sort VRAM | c sort CU | u sort CPU | 1-9 filter HCU | a all
```
</details>

Solid gradient bars (green → yellow → red), braille utilization waveforms
(one character = one second, 8 vertical levels), threshold coloring
(temperature ≥ 65 °C yellow / ≥ 75 °C red, power ≥ 80 %/90 % of cap), and
bordered panels.

## Quick start

**pip** — on a machine with python ≥ 3.7 and the Hygon hyhal driver
(see [Requirements](#requirements)):

```bash
pip install https://github.com/gongshl0306/dcutop/releases/download/v0.7.0/dcutop-0.7.0-py3-none-any.whl
dcutop --once
```

**uv** — when the machine's Python is too old. uv ships its own standalone
CPython, so the system interpreter does not matter:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
uv tool install --python 3.12 https://github.com/gongshl0306/dcutop/releases/download/v0.7.0/dcutop-0.7.0-py3-none-any.whl
dcutop
```

**Cluster deploy** — no pip on the target at all (single rsync):

```bash
./scripts/deploy.sh user@host /opt/dcutop
ssh user@host 'ln -sfn /opt/dcutop/bin/dcutop /usr/local/bin/dcutop'

# then, on any DCU node, any user:
dcutop                 # live TUI
dcutop --once          # one text snapshot
dcutop --json          # one JSON snapshot (stable schema, null = N/A)
```

**From source / without installing:**

```bash
PYTHONPATH=src python3 -m dcutop --once     # on a DCU node
./bin/dcutop --backend mock                 # anywhere: deterministic 8-GPU simulation
pip install .                              # optional: proper install (console script)
```

## Why

Hygon DCU servers ship with `hy-smi`, a batch text tool. There was no
`nvitop` for them. dcutop fills that gap while keeping the deployment story
of a cluster tool: **one rsync, no pip, no root install required**.

- **Zero dependencies** — `ctypes` (driver FFI) + `curses` (TUI) + `/proc`
  parsing. If `python3 ≥ 3.7` runs, dcutop runs.
- **Honest numbers** — every metric is unit-normalized at the backend
  (m°C → °C, µW → W, Hz → MHz); unsupported fields render as `N/A`, never 0.
- **Validated against `hy-smi`** under real inference load; the host CPU%
  matches `top` (busy excludes idle/iowait/steal — an earlier build counted
  idle and always showed ~100 %, caught by comparing against `top`).
- **Noise-proof UI** — windowed metrics are sampled by a background
  collector that rotates across devices, so the UI never blocks on the
  driver, and a failing read degrades to `N/A` instead of crashing.

## Requirements

| What | Why |
|---|---|
| Linux, `python3 ≥ 3.7` | standard library only |
| Hygon hyhal driver stack | `/opt/hyhal/lib/librocm_smi64.so` (or `DCUTOP_LIBRARY_PATH=/dir`) |
| Loaded kernel driver | `/dev/kfd`, `/dev/dri/renderD*` present |
| Read access to device nodes | works as non-root when nodes are group/world-writable (verified) |

Other Hygon DCU generations that ship the same RSMI interface should work;
unsupported metrics degrade to `N/A`. Not applicable to NVIDIA GPUs; AMD
ROCm shares API ancestry but is untested. Without a driver you get a clean,
actionable error (searched paths + hints), never a traceback.

## CLI

| Option | Meaning |
|---|---|
| `-d, --device 0,1,3` | watch only these HCUs (filters the process table too) |
| `--interval SEC` | refresh period (default 1.0) |
| `--window-ms MS` | HCU%/CU% sampling window per device (default 150) |
| `--once` | print one snapshot as text and exit |
| `--json` | print one snapshot as JSON and exit |
| `--backend mock` | deterministic simulation without hardware |
| `--frames N` | headless: render N refreshes, print the last frame, exit |
| `--version` | print version |

TUI keys: `q` quit · `r` redraw · `↑/↓` select · `p/m/c/u` sort by
PID/VRAM/CU%/CPU% · `1-9` filter HCUs · `a` show all.

### JSON

```json
{
  "dcutop_version": "0.5.2",
  "timestamp": 1788489077.1,
  "host": {"cpu_percent": 2.2, "memory_percent": 8.2},
  "devices": [{
      "index": 0, "name": "HYGON DCU-3G", "pci_bus_id": "0000:05:00.0",
      "numa_node": 0, "cu_count": 64,
      "utilization": 100.0, "cu_utilization": 84.9,
      "memory_used": 137408905216, "memory_total": 154602045440,
      "temperature": {"edge": 44.0, "junction": 50.0, "memory": 55.0, "core": 41.0},
      "power": 323.0, "power_cap": 800.0, "sclk_mhz": 1350.0, "mclk_mhz": 875.0
  }],
  "processes": [{
      "pid": 69131, "username": "root", "command": "sglang::scheduler_TP0",
      "cpu_percent": 99.0, "host_memory": 934598656, "host_memory_percent": 0.9,
      "devices": {"0": {"vram_used": 145681686528, "cu_occupancy": 7.8, "sdma_usage": 0}}
  }],
  "errors": []
}
```

## Architecture

```
TUI (curses) / CLI / --json
        │  consumes SystemSnapshot only (incl. per-device history)
    Collector (background thread: instant metrics every tick for all
               devices + rotating blocking-window HCU%/CU% samples)
        │
    HCUBackend protocol
    ┌────┴──────────┐
 NativeBackend    MockBackend
    │
 ffi/rsmi.py (ctypes) → librocm_smi64.so → HCU kernel driver → DCU
 host/proc.py (/proc)  → USER / CPU% / RSS / COMMAND
```

The backend fetches raw data and converts units, the collector samples and
caches, models define the data contract, the UI only renders. Development
works on any machine via the mock backend; the test suite (193 unittest
cases) needs no hardware.

## Metric semantics (validated under load)

- **HCU% / CU%** — driver-sampled windows (`rsmi_dev_hcu_util_get` /
  `rsmi_dev_cu_util_get`, 150 ms) rotated across devices: ~2.7 s per full
  sweep on 8 cards; each card shows its latest window until refreshed.
  The driver offers no non-blocking utilization counter — all three
  candidate APIs return sentinel data on current Hygon drivers.
- **VRAM** — as reported by `rsmi_dev_memory_usage_get`. ~94 % at idle is
  driver-reserved HBM (matches hy-smi), deliberately not alarmed.
- **Power** — `rsmi_dev_power_get` (µW → W); cap typically 800 W.
- **Temperatures** — edge / junction / memory / core sensors.
- **Process rows** — per-device VRAM from
  `rsmi_compute_process_info_by_device_get`, CU% preferring
  `rsmi_dev_proc_usage_get`; USER / RSS / CPU% / COMMAND parsed from /proc.
- **Host CPU%** matches `top` (busy = user+nice+system+irq+softirq,
  normalized by core count); **host MEM%** = (total − available) / total.

## Known limitations

- Read-only by design: no clock/power control, reset, MIG, or kill.
- HCU%/CU% lag up to ~2.7 s on 8 cards (blocking-window sampling is the
  only real source on this driver).
- No PCIe throughput, ECC, Hylink topology, CSV logging, or container
  attribution yet (the PCIe fields are already probed and documented).
- Verified on BW1100-class hardware; other generations may show `N/A`.

## Python API

dcutop also ships a small read-only Python API (nvitop-style facade):

```python
from dcutop import Device, snapshot

Device.count()                       # 8
dev = Device(0)
dev.name                             # 'HYGON DCU-3G'
dev.memory_used_human()              # '136.2G'

m = dev.snapshot()                   # windowed HCU%/CU% + instant metrics
m.power, m.temperature.edge          # 323.0, 44.0

for proc in dev.processes():         # processes on THIS device
    print(proc.pid, proc.username, proc.vram_used_human(0))

snap = snapshot()                    # whole-system SystemSnapshot
```

A background collector with callbacks is available for custom integrations
(logging, dashboards, agent loops):

```python
from dcutop import Collector, MockBackend

def on_collect(snap):
    print(snap.timestamp, snap.devices[0].utilization)
    return True   # return False to stop

Collector(MockBackend(), interval=1.0, on_collect=on_collect).start()
```

No hardware? `Device.use_mock()` (or `--backend mock`) switches to a
deterministic simulator — the API behaves identically.

## Contributing

```bash
PYTHONPATH=src python3 -m unittest discover -v   # 193 tests, no hardware needed
./bin/dcutop --backend mock --frames 3            # headless preview of one frame
```

The FFI ground truth (verified signatures, struct sizes, driver quirks)
is documented inline in `ffi/rsmi.py` — read it before changing the
bindings. PRs welcome: bug fixes, new read-only metrics, packaging.

## License

[MIT](LICENSE)
