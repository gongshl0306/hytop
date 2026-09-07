# hytop

`nvitop` 风格的海光 DCU（HCU）只读监控工具。零第三方依赖——ctypes 直连
`/opt/hyhal/lib/librocm_smi64.so`，标准库 curses 做 TUI，`/proc` 解析补齐
进程的 USER / CPU% / MEM% / COMMAND。

```
$ hytop   （TUI 实际效果，带颜色）

┌──────────────────────────────────────────────────────┐
│ hytop 0.4.0  host: gpu-server02  devices: 4 ...      │
└──────────────────────────────────────────────────────┘
┌─ Devices ────────────────────────────────────────────┐
│ HCU  Model       Temp   Power  HCU%   ...            │  host: gpu-server02  devices: 4  Sep 07 16:02:11  host cpu 99.9%  mem 7.8%

Devices
HCU  Model       Temp   Power  HCU%                              CU%  VRAM                                SCLK   MCLK
  0  DCU-3G      42.0C    387W  ▏██████████████████████  100.0%  84.9%  ▏██████████████  136.2/144.0G  1350M   875M
  1  DCU-3G      42.0C    360W  ▏██████████████████████  100.0%  77.1%  ▏██████████████  135.0/144.0G  1350M   875M
  2  DCU-3G      48.0C    374W  ▏██████████████████████  100.0%  75.8%  ▏██████████████  135.0/144.0G  1350M   875M
  3  DCU-3G      52.0C    371W  ▏██████████████████████  100.0%  85.3%  ▏██████████████  135.0/144.0G  1350M   875M

AVG GPU UTL: 92.3%
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣇⣇⣇⣧⣧⣇⣇⣇⡧⡧⡧⡧⡧⣇⣇⣇⣇⣧⣧⣇⡧⡧⡧⡧⡧⡧⡧⣇⣇⣇⣇⣇⣇⣇⣇⣇⣇⣇
⡀⡀⡀⡀⡀⡀⡀⡀⡀⡀⢠⢠⡠⡠⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
AVG GPU MEM: 93.7%
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
                                                          60s        30s

Processes:
    PID  USER     HCU    VRAM   CU%   CPU%  MEM%  COMMAND
>  69131  root       0  135.0G   7.8  19.5   0.8  sglang::scheduler_TP0
```

面板盒分区（信息 / Devices / Utilization / Processes，行间分隔线）、
实心渐变条形图（绿→黄→红）、AVG GPU UTL/MEM 盲文点阵历史波形 + 时间轴、
列宽自适应终端；阈值变色：温度 ≥65°C 黄 ≥75°C 红、功耗
≥80%/90% 功耗墙变色。

## 快速开始

目标机要求：Linux、`python3 >= 3.8`、HCU 驱动位于 `/opt/hyhal`（或用
`HYTOP_LIBRARY_PATH` 指定库目录）。**目标机无需 pip、无需安装任何依赖。**

```bash
# 部署到 DCU 节点（默认 x8950_2），可选中安装到 /opt 并进 PATH
./scripts/deploy.sh x8950_2 /opt/hytop
ssh x8950_2 'ln -sfn /opt/hytop/bin/hytop /usr/local/bin/hytop'

# 之后目标机上直接使用（任意用户、任意目录）
hytop --once
hytop --json
ssh -t x8950_2 hytop        # 交互式 TUI

# 或不安装、临时试用
./scripts/deploy.sh x8950_2 /tmp/hytop
ssh x8950_2 'PYTHONPATH=/tmp/hytop/src python3 -m hytop --once'
```

本机开发（无卡环境）：

```bash
./bin/hytop --backend mock          # 确定性模拟
PYTHONPATH=src python3 -m unittest  # 全量单元测试，不依赖真卡
```

## 命令行

| 参数 | 说明 |
|---|---|
| `-d, --device 0,1,3` | 只看指定卡（同时过滤进程表） |
| `--interval SEC` | 刷新周期（默认 1s） |
| `--window-ms MS` | HCU%/CU% 的采样窗口（默认 150ms/卡） |
| `--once` | 打印一次快照并退出 |
| `--json` | 打印一次 JSON 快照并退出（schema 稳定，null = 不支持） |
| `--backend mock` | 无硬件模拟数据源 |
| `--frames N` | 无头渲染 N 帧后打印最后一帧并退出（测试/无 pty 环境） |
| `--version` | 版本号 |

TUI 按键：`q` 退出 | `r` 重绘 | `↑/↓` 选择 | `p/m/c/u` 按 PID/VRAM/CU%/CPU%
排序 | `1-9` 过滤卡 | `a` 显示全部。

## 架构

```
TUI(curses) / CLI / --json
        │  只消费 SystemSnapshot（含每卡历史）
    Collector（后台线程：瞬时指标每轮全采，阻塞式 HCU%/CU% 窗口每轮 3 卡轮转）
        │
    HCUBackend 协议
    ┌────┴─────────┐
 NativeBackend   MockBackend
    │
 ffi/rsmi.py (ctypes) → librocm_smi64.so → HCU 驱动 → DCU
 host/proc.py (/proc)  → USER/CPU%/RSS/COMMAND
```

## 指标口径（v0.2，均经真机带负载对拍）

- **HCU%**：窗口值（`rsmi_dev_hcu_util_get`，150ms，后台每轮 3 卡轮转，
  全卡 ~2.7s 刷新一轮，其余时间显示该卡上次测量值）
- **CU%**：窗口值（`rsmi_dev_cu_util_get`，窗口内平均 CU 占用）；负载下
  典型 75-85%
- **VRAM**：`rsmi_dev_memory_usage_get`，bytes。**注意：空载即 ~94% 是驱动
  报告的预留 HBM 占用**（与 hy-smi VRAM% 95% 一致），不是泄漏，故不做变色告警
- **Power**：`rsmi_dev_power_get`（µW→W）；空载 ~150W，推理满载 360-400W
- **Temp**：Edge/Junction/Memory/Core 四传感器
- **SCLK**：负载自动升档（1200→1350MHz）可见
- **进程 CU%**：优先 `rsmi_dev_proc_usage_get`（浮点、负载下真实），
  回退 by_device 占用、v2 rate
- 任一指标读取失败显示 **N/A**，绝不显示 0 冒充

### 为什么 HCU% 不是每秒实时

本驱动（librocm_smi64.so.2.8）的三个瞬时利用率 API 全部未实现
（`rsmi_utilization_count_get` 恒 0xFFFFFFFF、`activity_metric_get` 不跟随
负载、gpu_metrics 表 utilization 字段为哨兵值，详见
[docs/ffi-notes.md](docs/ffi-notes.md)）——阻塞式窗口采样是唯一真实来源，
因此采用轮转策略。

## 已知限制（v0.2）

- 只读监控：无设频/功耗/复位/MIG/kill 等控制操作
- HCU%/CU% 有最多 ~2.7s 的轮转滞后（驱动仅提供阻塞窗口采样所迫）
- 未实现：PCIe 吞吐列（接口已探明可用，见 ffi-notes）、ECC、Hylink 拓扑、
  进程 kill、CSV 落盘、容器感知
- 在 BW1100（HYGON DCU-3G，dev 0x6430）上验证；其他代际可能有个别指标 N/A

## 开发

```bash
PYTHONPATH=src python3 -m unittest discover -v   # 全量测试
./bin/hytop --backend mock --frames 3            # 无头看一帧
```

Layout: `src/hytop/{models,backends,ffi,collector,host,tui}` — Backend 负责
拿准原始数据，Collector 负责采样缓存，models 提供稳定数据模型，UI 只展示。
