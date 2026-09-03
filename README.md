# hytop

`nvitop` 风格的海光 DCU（HCU）只读监控工具。零第三方依赖——ctypes 直连
`/opt/hyhal/lib/librocm_smi64.so`，标准库 curses 做 TUI，`/proc` 解析补齐
进程的 USER / CPU% / MEM% / COMMAND。

```
$ hytop --once

hytop 0.1.0  host: sbmc  devices: 8
HCU  Model        Temp   Power   HCU%    CU%             VRAM   SCLK   MCLK
  0  DCU-3G        34.0C  162.0W   0.0%   0.0%    136.2G/144.0G  1200M   875M
  1  DCU-3G        35.0C  149.0W   0.0%   0.0%    135.0G/144.0G  1200M   875M
  ...

    PID  USER     DEV      VRAM   CU%   CPU%  MEM%  COMMAND
 69132   root       1    135.0G   0.0  98.9   0.8  sglang::scheduler_TP1
 70118   root       6    134.8G   0.0  94.0   0.8  sglang::scheduler_TP2
  ...
```

## 快速开始

目标机要求：Linux、`python3 >= 3.8`、HCU 驱动位于 `/opt/hyhal`（或用
`HYTOP_LIBRARY_PATH` 指定库目录）。**目标机无需 pip、无需安装任何依赖。**

```bash
# 部署到 DCU 节点（默认 x8950_2）
./scripts/deploy.sh x8950_2

# 一次性快照 / JSON
ssh x8950_2 'PYTHONPATH=/tmp/hytop/src python3 -m hytop --once'
ssh x8950_2 'PYTHONPATH=/tmp/hytop/src python3 -m hytop --json'

# 交互式 TUI
ssh -t x8950_2 'PYTHONPATH=/tmp/hytop/src python3 -m hytop'
```

本机开发（无卡环境）：

```bash
./bin/hytop --backend mock          # 确定性模拟 8 卡
PYTHONPATH=src python3 -m unittest  # 148 个单元测试，不依赖真卡
```

## 命令行

| 参数 | 说明 |
|---|---|
| `-d, --device 0,1,3` | 只看指定卡（同时过滤进程表） |
| `--interval SEC` | 刷新周期（默认 1s） |
| `--window-ms MS` | HCU%/CU% 的采样窗口（默认 200ms/卡） |
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
        │  只消费 SystemSnapshot
    Collector（后台线程：瞬时指标每轮全采，阻塞式 HCU%/CU% 窗口逐卡轮转）
        │
    HCUBackend 协议
    ┌────┴─────────┐
 NativeBackend   MockBackend
    │
 ffi/rsmi.py (ctypes) → librocm_smi64.so → HCU 驱动 → DCU
 host/proc.py (/proc)  → USER/CPU%/RSS/COMMAND
```

## 指标口径（v0.1）

- **HCU%**：窗口值（`rsmi_dev_hcu_util_get`，默认 200ms，后台逐卡轮转，
  8 卡约 4s 全量刷新一轮，其余时间显示上次测量值）
- **CU%**：窗口值（`rsmi_dev_cu_util_get`，窗口内平均 CU 占用）
- **VRAM**：`rsmi_dev_memory_usage_get`，bytes。**注意：空载即显示 ~94%
  是驱动报告的预留 HBM 占用**（与 hy-smi 的 VRAM% 95% 一致），不是泄漏
- **Power**：`rsmi_dev_power_get`（µW→W，本机型返回平均功率）；PowerCap 800W
- **Temp**：Edge / Junction / Memory / Core 四传感器（milli-°C→°C）
- **SCLK/MCLK**：当前频率档（Hz→MHz），deep sleep 时显示 N/A
- **进程**：`rsmi_compute_process_info_by_device_get` 提供每卡显存；
  CPU% 为 top 口径（可超 100%）；USER/MEM% 来自 /proc
- 任一指标读取失败显示 **N/A**，绝不显示 0 冒充

## 已知限制（v0.1）

- 只读监控：无设频/功耗/复位/MIG/kill 等控制操作
- HCU%/CU% 有最多约 4s 的轮转滞后（阻塞窗口测量所迫）
- 未实现：PCIe 吞吐、ECC、Hylink 拓扑、历史曲线、远程多节点
- 仅在 BW1100（HYGON DCU-3G，dev 0x6430，librocm_smi64.so.2.8）上验证；
  其他代际可能有个别指标 N/A
- FFI 依据与已验证事实见 [docs/ffi-notes.md](docs/ffi-notes.md)

## 开发

```bash
PYTHONPATH=src python3 -m unittest discover -v   # 全量测试
./bin/hytop --backend mock --frames 3            # 无头看一帧
```

Layout: `src/hytop/{models,backends,ffi,collector,host,tui}` — Backend 负责
拿准原始数据，Collector 负责采样缓存，models 提供稳定数据模型，UI 只展示。
