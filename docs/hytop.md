`hytop` 第一版我建议不要走 `hy-smi` 文本解析，而是直接把它设计成一个真正类似 `nvitop` 的项目：

> **HCU Driver → `librocm_smi64.so` / `libhydmi.so` → Python Backend → Collector → TUI**

目前海光公开的最新项目已经是 **`HYGON-AI/hcu-dcgm/v3`**，官方说明运行时直接依赖 `/opt/hyhal/lib/libhydmi.so` 和 `librocm_smi64.so`，仓库 `pkg/dcgm/include/` 也保留了构建需要的驱动接口头文件。因此 `hytop` 可以参考它的实现来完成 Python binding，而不需要解析 `hy-smi` 输出。

## 1. 第一版目标

项目名：

```text
hytop
```

第一版 `v0.1.0` 先只做 **监控，只读，不做控制操作**。

目标效果：

```text
$ hytop

 hytop 0.1.0                    host: worker-01
 HCU Driver: 6.x                Devices: 8
─────────────────────────────────────────────────────────────────────
 HCU  Model     Temp   Power    HCU%   CU%     VRAM        SCLK
  0   BW1100     58C    412W     96%    94%   58.2/64G    1400M
  1   BW1100     61C    425W     98%    96%   58.2/64G    1400M
  2   BW1100     55C    386W     82%    79%   42.1/64G    1350M
  ...

────────────────────────── Processes ─────────────────────────────────
 HCU PID       USER     HCU%    CU%    VRAM      CPU%   MEM% COMMAND
 0   184221    root      96%     94%   51.2G     105%    1.2 python
 1   184221    root      97%     95%   51.0G     105%    1.2 python
 4   192844    root      82%     78%   32.4G      98%    0.8 vllm

 q quit | r refresh | ↑↓ select | c sort CU | m sort VRAM | p sort PID
```

第一版覆盖：

- HCU 枚举
- 型号
- PCI BDF
- NUMA
- HCU Busy
- CU Util
- VRAM Total / Used / Free
- 温度
- 功耗
- SCLK/MCLK
- PID
- 每 PID 显存
- CU Occupancy
- SDMA
- USER
- CPU %
- Host MEM %
- COMMAND
- 多卡进程
- 1 秒左右动态刷新

官方 HCU DCGM 已经公开了 `DevBusyPercent()`、`DevCuUtil()`、`Power()`、`GetDeviceTemperatureInfo()`、`ProcessHCUInfo()`、`ProcessInfoByDevice()` 等接口，说明这些数据底层确实能够获得。

---

# 2. 整体架构

我建议这样分层：

```text
                         hytop
                           │
                ┌──────────┴──────────┐
                │                     │
               CLI                   API
                │                     │
                └──────────┬──────────┘
                           │
                         TUI
                           │
                      Collector
                           │
                       Data Model
                           │
                   HCUBackend Protocol
                           │
          ┌────────────────┴────────────────┐
          │                                 │
   NativeBackend                      DcgmBackend
     默认后端                           备用/调试
          │                                 │
   Python ctypes/cffi               HTTP localhost
          │                                 │
   ┌──────┴──────┐                   hcu-dcgm
   │             │
librocm_smi   libhydmi
   │             │
   └──────┬──────┘
          │
      HCU Driver
          │
         DCU
```

关键思想：

> **UI 永远不知道底层是 librocm_smi、libhydmi 还是 hcu-dcgm。**

这样后面甚至可以增加：

```text
NativeBackend
DcgmBackend
MockBackend
```

Mock 特别重要，没有 DCU 的开发机也能开发 UI。

---

# 3. 项目目录

建议直接这样：

```text
hytop/
├── pyproject.toml
├── README.md
├── LICENSE
│
├── src/
│   └── hytop/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       │
│       ├── api/
│       │   ├── __init__.py
│       │   ├── device.py
│       │   ├── process.py
│       │   └── system.py
│       │
│       ├── models/
│       │   ├── device.py
│       │   ├── process.py
│       │   └── snapshot.py
│       │
│       ├── backends/
│       │   ├── base.py
│       │   ├── native.py
│       │   ├── dcgm.py
│       │   └── mock.py
│       │
│       ├── ffi/
│       │   ├── loader.py
│       │   ├── rsmi.py
│       │   ├── hydmi.py
│       │   ├── structs.py
│       │   └── errors.py
│       │
│       ├── collector/
│       │   ├── collector.py
│       │   └── cache.py
│       │
│       ├── host/
│       │   └── process.py
│       │
│       └── tui/
│           ├── app.py
│           ├── device_panel.py
│           ├── process_table.py
│           └── formatter.py
│
└── tests/
    ├── test_device.py
    ├── test_process.py
    ├── test_collector.py
    └── test_mock.py
```

依赖第一版控制得很少：

```toml
dependencies = [
    "psutil>=5.9",
    "rich>=13",
    "textual>=0.80",
]
```

如果追求 `nvitop` 那种极简依赖，可以后面把 Textual 换为 curses。

但 **第一版开发效率我建议 Textual**。

---

# 4. 最重要的一层：Backend

这个接口必须先定下来。

`backends/base.py`：

```python
from abc import ABC, abstractmethod
from hytop.models.device import DeviceInfo, DeviceMetrics
from hytop.models.process import HcuProcessInfo


class HCUBackend(ABC):

    @abstractmethod
    def init(self) -> None:
        ...

    @abstractmethod
    def shutdown(self) -> None:
        ...

    @abstractmethod
    def device_count(self) -> int:
        ...

    @abstractmethod
    def device_info(self, index: int) -> DeviceInfo:
        ...

    @abstractmethod
    def device_metrics(self, index: int) -> DeviceMetrics:
        ...

    @abstractmethod
    def processes(self) -> list[HcuProcessInfo]:
        ...

    @abstractmethod
    def process_info(
        self,
        pid: int,
        device_index: int,
    ) -> HcuProcessInfo | None:
        ...
```

以后 UI 只调用：

```python
backend.device_metrics(0)
```

绝对不要出现：

```python
ui -> ctypes -> rsmi_xxx()
```

这种耦合。

---

# 5. 数据结构

这个也是整个项目最值得先定好的东西。

## DeviceInfo

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceInfo:
    index: int

    name: str | None
    pci_bus_id: str | None
    device_id: str | None
    unique_id: str | None

    numa_node: int | None

    memory_total: int | None

    cu_count: int | None
```

注意：

> 内部所有显存统一使用 `bytes`。

不要 Backend A 返回 MiB，Backend B 返回 GB。

---

## 温度

```python
@dataclass
class TemperatureInfo:
    edge: float | None = None
    junction: float | None = None
    memory: float | None = None
    core: float | None = None
```

这个结构正好对应现在 HCU DCGM 提供的四类：

- Edge
- Junction
- Memory
- Core

官方接口就是 `GetDeviceTemperatureInfo()`。

---

## DeviceMetrics

```python
@dataclass
class DeviceMetrics:
    index: int

    utilization: float | None
    cu_utilization: float | None

    memory_used: int | None
    memory_total: int | None

    temperature: TemperatureInfo

    power: float | None
    power_cap: float | None

    sclk_mhz: float | None
    mclk_mhz: float | None

    pcie_tx_bytes_per_sec: float | None = None
    pcie_rx_bytes_per_sec: float | None = None
```

统一约定：

```text
utilization      0 ~ 100
cu_utilization   0 ~ 100

memory           bytes

temperature      °C

power            W

clock            MHz

bandwidth         bytes/s
```

这个非常重要。

例如官方 `DevCuUtil()` 文档指出某些版本返回值语义通常是：

```text
0 ~ 1
```

所以 Backend 层负责转换：

```python
cu_percent = raw * 100
```

不能让 UI 猜单位。

---

# 6. Process 数据模型

这里尤其要考虑一个 PID 同时用多张卡。

不要设计成：

```text
PID -> GPU
```

而应该：

```text
PID
 ├─ HCU0 usage
 ├─ HCU1 usage
 ├─ HCU2 usage
 └─ HCU3 usage
```

官方 `ProcessHCUInfo()` 的结构本身就包含：

```text
ProcessID
ProcessName
Pasid
VramUsage
SdmaUsage
CuOccupancy
MinorNumbers[]
```

而且还有 `ProcessInfoByDevice(pid, device)`。

所以：

```python
@dataclass
class ProcessDeviceUsage:
    device_index: int

    vram_used: int | None
    cu_occupancy: float | None
    sdma_usage: int | None
```

然后：

```python
@dataclass
class HcuProcessInfo:
    pid: int
    name: str | None
    pasid: int | None

    devices: dict[int, ProcessDeviceUsage]

    username: str | None = None
    command: str | None = None

    cpu_percent: float | None = None
    host_memory: int | None = None
    host_memory_percent: float | None = None
```

GPU/HCU 信息来自：

```text
librocm_smi64 / libhydmi
```

Host 信息来自：

```text
psutil
```

---

# 7. Python 对外 API

对用户不要暴露 Backend。

最终目标是支持这种代码。

## 最基础

```python
from hytop import Device

print(Device.count())

devices = Device.all()

for dev in devices:
    print(dev.index)
    print(dev.name)
```

使用：

```python
dev = Device(0)

print(dev.utilization())
print(dev.cu_utilization())

print(dev.memory_total())
print(dev.memory_used())

print(dev.temperature())
print(dev.power())

print(dev.processes())
```

---

## snapshot

我更推荐：

```python
dev = Device(0)

snapshot = dev.snapshot()

print(snapshot.utilization)
print(snapshot.cu_utilization)

print(snapshot.memory_used)
print(snapshot.memory_total)

print(snapshot.temperature.core)

print(snapshot.power)
```

因为：

```python
dev.power()
dev.temp()
dev.util()
dev.memory()
```

会导致连续执行多个 FFI 调用。

而：

```python
dev.snapshot()
```

更方便以后做缓存。

---

# 8. 推荐的正式 Python API

例如：

```python
from hytop import Device

devices = Device.all()

for device in devices:
    snapshot = device.snapshot()

    print(
        device.index,
        device.name,
        snapshot.utilization,
        snapshot.memory_used,
        snapshot.temperature.core,
        snapshot.power,
    )
```

进程：

```python
from hytop import processes

for proc in processes():
    print(proc.pid)
    print(proc.username)
    print(proc.command)

    for index, usage in proc.devices.items():
        print(
            index,
            usage.vram_used,
            usage.cu_occupancy,
        )
```

API 风格尽量往 `nvitop` 靠。

---

# 9. Native Backend

这里是真正与驱动交互的地方。

```text
native.py
   │
   ├── rsmi.py
   │      └── librocm_smi64.so
   │
   └── hydmi.py
          └── libhydmi.so
```

加载顺序：

```python
/opt/hyhal/lib/librocm_smi64.so
/opt/hyhal/lib/libhydmi.so
```

也支持：

```bash
export HYTOP_LIBRARY_PATH=/opt/hyhal/lib
```

loader：

```python
SEARCH_PATHS = [
    os.environ.get("HYTOP_LIBRARY_PATH"),
    "/opt/hyhal/lib",
    "/opt/dtk/lib",
]
```

官方 HCU DCGM 当前默认就是依赖 `/opt/hyhal/lib` 下的这些动态库。

---

# 10. FFI 不要一次写太多

第一版只绑定最核心接口。

例如：

```text
初始化
设备数量
Device ID
PCI ID

VRAM total
VRAM used

busy percent

temperature

power

SCLK
MCLK

process list
process by device
```

类似：

```python
class RsmiAPI:

    def init(self):
        ...

    def shutdown(self):
        ...

    def device_count(self) -> int:
        ...

    def busy_percent(self, device: int) -> float:
        ...

    def memory_total(self, device: int) -> int:
        ...

    def memory_used(self, device: int) -> int:
        ...

    def temperature(self, device: int) -> TemperatureInfo:
        ...

    def power(self, device: int) -> float:
        ...

    def processes(self):
        ...
```

**底层 C 函数原型不要凭 AMD ROCm 文档硬写。**

应该以：

```text
HYGON-AI/hcu-dcgm/v3/pkg/dcgm/include/
```

中的实际头文件以及：

```text
pkg/dcgm/api.go
```

里的 CGO 调用作为实现依据。

这是后面 Agent 写代码时非常重要的一条。

---

# 11. 推荐 ctypes 而不是直接依赖 hcu-dcgm

第一版关系建议是：

```text
hytop
 ↓
ctypes
 ↓
HCU driver library
```

而：

```text
HYGON-AI/hcu-dcgm
```

作为：

> **驱动 API 的参考实现**

不要变成：

```text
hytop
 ↓
HTTP
 ↓
dcgm service
 ↓
driver
```

否则用户使用 `hytop` 之前还得：

```bash
systemctl start hcu-dcgm
```

就不像 `nvitop` 了。

不过保留一个：

```python
DcgmBackend
```

对于开发和排障非常有用。

---

# 12. Collector 一定要单独一层

千万别让 Textual 的刷新函数直接读硬件。

应该：

```text
                       ┌────────── TUI 100ms render
                       │
Driver → Collector → Cache
                       │
                       └────────── API
```

例如：

```python
class Collector:

    def __init__(
        self,
        backend,
        interval=1.0,
    ):
        self.backend = backend
        self.interval = interval
        self.snapshot = None

    def collect(self):
        ...
```

采样周期第一版：

```text
HCU busy       1s
CU             1s
Memory         1s
Power          1s
Temperature    1s
Processes      1s

Clock          2s
PCIe           2s

Topology       启动时一次
Device name    启动时一次
PCI BDF        启动时一次
NUMA           启动时一次
```

这样不会无意义地反复读取静态数据。

---

# 13. 完整 Snapshot

整个 TUI 每次只消费一个东西：

```python
@dataclass
class SystemSnapshot:

    timestamp: float

    devices: dict[int, DeviceMetrics]

    processes: list[HcuProcessInfo]

    cpu_percent: float
    memory_percent: float

    errors: list[str]
```

这样：

```text
硬件数据
   ↓
Collector
   ↓
SystemSnapshot
   ↓
TUI
```

UI 本身不会因为某个驱动 API 报错直接挂掉。

例如温度读取失败：

```text
HCU0 Temp: N/A
```

而不是：

```text
hytop crashed
```

---

# 14. Unsupported 也要作为正常状态处理

这对于 DCU 特别重要。

不同：

```text
DCU 代际
驱动版本
DTK 版本
固件版本
```

支持的指标可能不同。

所以不要：

```python
except:
    return 0
```

因为：

```text
0 W
0 °C
0 MB
```

会严重误导。

统一：

```python
None
```

UI 显示：

```text
N/A
```

例如：

```python
power: float | None
```

---

# 15. FFI 异常

定义自己的异常：

```python
class HytopError(Exception):
    pass


class DriverNotFoundError(HytopError):
    pass


class DriverInitError(HytopError):
    pass


class DeviceNotFoundError(HytopError):
    pass


class MetricNotSupportedError(HytopError):
    pass


class PermissionDeniedError(HytopError):
    pass
```

例如启动：

```text
$ hytop

hytop: HCU driver libraries not found.

Searched:
  /opt/hyhal/lib/librocm_smi64.so
  /opt/hyhal/lib/libhydmi.so

Check:
  hy-smi
  ls /opt/hyhal/lib
```

这种体验要比：

```text
OSError: cannot open shared object file
```

好很多。

---

# 16. CLI

第一版支持：

```bash
hytop
```

指定卡：

```bash
hytop -d 0
```

或者：

```bash
hytop -d 0,1,2,3
```

刷新：

```bash
hytop --interval 2
```

只打印一次：

```bash
hytop --once
```

非常建议做这个：

```bash
hytop --json
```

例如：

```json
{
  "devices": [
    {
      "index": 0,
      "utilization": 96,
      "memory_used": 55123512320,
      "power": 412,
      "temperature": 58
    }
  ]
}
```

它以后可以直接用于：

```text
Shell
Agent
Prometheus exporter
故障诊断程序
```

---

# 17. TUI 第一版布局

不用一开始做得太花。

先三层：

```text
┌──────────────── Host ─────────────────────────┐
│ hytop 0.1  Host worker01  HCU:8  Interval:1s │
└───────────────────────────────────────────────┘

┌──────────────── Devices ──────────────────────────────────────┐
│ HCU Model  Temp Power HCU% CU%  VRAM       SCLK MCLK PCIe   │
│ 0   BW1100 58C  420W  96   94   58/64GB    1400 1800 G4x16 │
│ 1   BW1100 57C  417W  95   93   58/64GB    1400 1800 G4x16 │
└───────────────────────────────────────────────────────────────┘

┌──────────────── Processes ────────────────────────────────────┐
│ HCU PID      USER VRAM   CU% CPU% MEM% TIME COMMAND          │
│ 0   123332   root 51G    95   110  1.4  4h   python         │
│ 1   123332   root 51G    96   110  1.4  4h   python         │
└───────────────────────────────────────────────────────────────┘
```

按键第一版：

```text
q       quit
r       refresh

↑ ↓     select

p       sort PID
m       sort VRAM
c       sort CU
u       sort HCU util

1-8     filter HCU
a       all HCU
```

---

# 18. 第一版不要做这些

我建议暂时不要：

```text
设置 SCLK
设置 MCLK
设置 PowerCap

Reset HCU
Reset ECC

MIG/vHCU 创建
进程 kill

RAS 历史
PCIe AER
Hylink 实时流量

Prometheus
Web UI
Remote node
```

因为 `hytop 0.1` 最关键的是：

> **先把监控链路做稳。**

---

# 19. 第二阶段就很有意思了

后面可以演进：

```text
hytop 0.2
├── PCIe Gen / Width
├── PCIe Rx / Tx
├── NUMA
├── Hylink topology
├── UMC bandwidth
├── ECC CE / UE
├── temperature sensors
└── historical sparkline
```

目前官方 HCU DCGM v3 已经可以看到 Hylink 判断、PCIe、UMC、ECC 等能力，例如 `TopoIsHylink()`、`EccCount()`，因此这些非常适合后面继续加。

再到：

```text
hytop 0.3

HCU0 ──HSL── HCU1
 │             │
PCIe          PCIe
 │             │
CPU0          CPU3

PCIe Replay
HSL bandwidth
UMC bandwidth
ECC CE/UE
```

这时 `hytop` 对你们排查 DCU 服务器就会比单纯 `hy-smi` 有价值得多。

---

## 20. 我建议第一版开发顺序

严格按照这个顺序：

```text
① Backend Interface
        ↓
② ctypes loader
        ↓
③ device_count
        ↓
④ Device static info
        ↓
⑤ util / memory / temp / power
        ↓
⑥ Process list
        ↓
⑦ psutil 补 USER / CPU / CMD
        ↓
⑧ Collector + Snapshot
        ↓
⑨ --once
        ↓
⑩ --json
        ↓
⑪ Textual TUI
```

**不要先写 TUI。**

先做到：

```bash
hytop --once
```

输出：

```text
HCU 0  BW1100  96%  58.1/64G  58C  420W
HCU 1  BW1100  95%  58.1/64G  57C  415W
```

然后：

```bash
hytop --json
```

数据完全正确。

最后才上动态界面。

---

### 最终核心关系

```text
             hytop public API

 Device                 HcuProcess
    │                        │
    └──────────┬─────────────┘
               │
         SystemSnapshot
               ▲
               │
           Collector
               ▲
               │
          HCUBackend
               ▲
               │
         NativeBackend
               │
          ┌────┴────┐
          │         │
       RSMI       HYDMI
          │         │
  librocm_smi64   libhydmi
          └────┬────┘
               │
           HCU Driver
               │
           BW1000/BW1100
```

我会把 **`hytop` 的核心原则**定成一句：

> **Backend 负责“拿到准确的原始 HCU 数据”，Collector 负责“采样和缓存”，API 负责“提供稳定的数据模型”，TUI 只负责“展示”。**

按照这个架构做，`hytop` 后面不仅能成为 Hygon 版 `nvitop`，还可以很自然地继续长出 `hytop --json`、Prometheus exporter、Agent 工具调用和多节点 DCU 运维能力。