"""ctypes bindings for ``librocm_smi64`` — the HCU driver SMI library.

Ground truth is the driver header shipped on the target machine
(``/opt/hyhal/include/rocm_smi/rocm_smi.h``, librocm_smi64.so.2.8) plus an
on-machine smoke test (8x HYGON DCU-3G). Facts baked in here:

- ``RSMI_MAX_NUM_FREQUENCIES`` is **33** (32 normal + 1 sleep slot); a
  32-entry buffer would let the driver write past its end.
- ``rsmi_process_info_v2_t.vramUsageSize`` is **bytes** on this build even
  though the header comment claims MiB (93.73% == bytes/total exactly).
- v1 ``rsmi_compute_process_info_get`` returns valid pid/pasid but all-zero
  statistics on this driver; real per-PID numbers must come from the
  ``_v2`` per-pid call.
- Used VRAM is ``rsmi_dev_memory_usage_get`` (there is no
  ``rsmi_dev_memory_used_get`` in this library).
- Temperature unit: millidegrees C. Power: microwatts. Frequencies: Hz.
  Temp sensor types: EDGE=0 JUNCTION=1 MEMORY=2 ... CORE=11.
  Clock types: SYS=0 ... MEM=4.
- ``rsmi_dev_hcu_util_get``/``rsmi_dev_cu_util_get`` block for exactly
  ``duration`` milliseconds.

This class is a thin, faithful wrapper: pythonic names, plain Python types
out, :class:`RsmiCallError` on any non-success status. Unit conversion is
done here (backend responsibility) so no caller ever guesses units.
"""

from __future__ import annotations

import ctypes
from ctypes import (
    POINTER,
    byref,
    c_bool,
    c_char_p,
    c_float,
    c_int,
    c_int32,
    c_int64,
    c_size_t,
    c_uint16,
    c_uint32,
    c_uint64,
    c_void_p,
    create_string_buffer,
)

from dcutop.ffi.errors import DriverInitError, RsmiCallError

RSMI_MAX_NUM_FREQUENCIES = 33

RSMI_MEM_TYPE_VRAM = 0

RSMI_TEMP_CURRENT = 0
RSMI_TEMP_TYPE_EDGE = 0
RSMI_TEMP_TYPE_JUNCTION = 1
RSMI_TEMP_TYPE_MEMORY = 2
RSMI_TEMP_TYPE_CORE = 11

RSMI_CLK_TYPE_SYS = 0
RSMI_CLK_TYPE_MEM = 4


class RsmiFrequencies(ctypes.Structure):
    """rsmi_frequencies_t — sizeof must be 280 on the target."""

    _fields_ = [
        ("has_deep_sleep", c_bool),
        ("num_supported", c_uint32),
        ("current", c_uint32),
        ("frequency", c_uint64 * RSMI_MAX_NUM_FREQUENCIES),
    ]


class RsmiProcessInfo(ctypes.Structure):
    """rsmi_process_info_t (v1) — sizeof 32 on the target."""

    _fields_ = [
        ("process_id", c_uint32),
        ("pasid", c_uint32),
        ("vram_usage", c_uint64),
        ("sdma_usage", c_uint64),
        ("cu_occupancy", c_uint32),
    ]


class RsmiProcessInfoV2(ctypes.Structure):
    """rsmi_process_info_v2_t — sizeof 152 on the target.

    vramUsageSize is BYTES on this build (header comment says MiB; wrong).
    """

    _fields_ = [
        ("processId", c_uint32),
        ("vramUsageSize", c_uint64),
        ("vramUsageRate", c_float),
        ("usedGpus", c_int),
        ("gpuIndex", c_int * 16),
        ("gpuUsageRate", c_float * 16),
    ]


def mdeg_to_c(millidegrees: int | None) -> float | None:
    """Millidegrees Celsius -> degrees Celsius."""
    return None if millidegrees is None else millidegrees / 1000.0


def uw_to_w(microwatts: int | None) -> float | None:
    """Microwatts -> watts."""
    return None if microwatts is None else microwatts / 1_000_000.0


def hz_to_mhz(hertz: int | None) -> float | None:
    """Hertz -> MHz."""
    return None if hertz is None else hertz / 1_000_000.0


def bdf_str(bdfid: int | None) -> str | None:
    """Pack rsmi_dev_pci_id_get value into domain:bus:device.function.

    Encoding: bits 0-2 function, 3-7 device, 8-15 bus, 32+ domain.
    Verified against the target: raw 0x500 -> 0000:05:00.0 (lspci agrees).
    """
    if bdfid is None:
        return None
    domain = (bdfid >> 32) & 0xFFFFFFFF
    bus = (bdfid >> 8) & 0xFF
    device = (bdfid >> 3) & 0x1F
    function = bdfid & 0x7
    return f"{domain:04x}:{bus:02x}:{device:02x}.{function:x}"


class RsmiApi:
    """Bound prototypes for one loaded librocm_smi64 handle."""

    def __init__(self, lib: ctypes.CDLL):
        self._lib = lib
        b = self._bind
        b("rsmi_init", [c_uint64], c_int32)
        b("rsmi_shut_down", [], c_int32)
        b("rsmi_status_string", [c_int32, POINTER(c_char_p)], c_int32)
        b("rsmi_num_monitor_devices", [POINTER(c_uint32)], c_int32)
        b("rsmi_dev_name_get", [c_uint32, c_char_p, c_size_t], c_int32)
        b("rsmi_dev_id_get", [c_uint32, POINTER(c_uint16)], c_int32)
        b("rsmi_dev_pci_id_get", [c_uint32, POINTER(c_uint64)], c_int32)
        b("rsmi_topo_get_numa_node_number", [c_uint32, POINTER(c_uint32)], c_int32)
        b("rsmi_dev_cu_num_get", [c_uint32, POINTER(c_int)], c_int32)
        b(
            "rsmi_dev_memory_total_get",
            [c_uint32, c_uint32, POINTER(c_uint64)],
            c_int32,
        )
        b(
            "rsmi_dev_memory_usage_get",
            [c_uint32, c_uint32, POINTER(c_uint64)],
            c_int32,
        )
        b("rsmi_dev_busy_percent_get", [c_uint32, POINTER(c_uint32)], c_int32)
        b("rsmi_dev_power_get", [c_uint32, POINTER(c_uint64), POINTER(c_int32)], c_int32)
        b("rsmi_dev_power_ave_get", [c_uint32, c_uint32, POINTER(c_uint64)], c_int32)
        b("rsmi_dev_power_cap_get", [c_uint32, c_uint32, POINTER(c_uint64)], c_int32)
        b("rsmi_dev_temp_metric_get", [c_uint32, c_uint32, c_uint32, POINTER(c_int64)], c_int32)
        b("rsmi_dev_gpu_clk_freq_get", [c_uint32, c_uint32, POINTER(RsmiFrequencies)], c_int32)
        b("rsmi_dev_hcu_util_get", [c_uint32, c_uint32, POINTER(c_float)], c_int32)
        b("rsmi_dev_cu_util_get", [c_uint32, c_uint32, POINTER(c_float)], c_int32)
        b("rsmi_dev_proc_usage_get", [c_uint32, c_uint32, POINTER(c_float)], c_int32)
        b(
            "rsmi_compute_process_info_get",
            [POINTER(RsmiProcessInfo), POINTER(c_uint32)],
            c_int32,
        )
        b(
            "rsmi_compute_process_info_by_pid_get_v2",
            [c_uint32, POINTER(RsmiProcessInfoV2)],
            c_int32,
        )
        b(
            "rsmi_compute_process_info_by_device_get",
            [c_uint32, c_uint32, POINTER(RsmiProcessInfo)],
            c_int32,
        )

    def _bind(self, name: str, argtypes: list, restype) -> None:
        fn = getattr(self._lib, name)
        fn.argtypes = argtypes
        fn.restype = restype
        setattr(self, name, fn)

    def _call(self, name: str, *args):
        status = getattr(self, name)(*args)
        if status != 0:
            raise RsmiCallError(status, f"{name}: {self.status_string(status)}")
        return status

    def status_string(self, status: int) -> str:
        out = c_char_p()
        r = self.rsmi_status_string(c_int32(status), byref(out))
        if r != 0 or not out.value:
            return f"unknown rsmi status {status}"
        return out.value.decode(errors="replace")

    # -- lifecycle ---------------------------------------------------------

    def init(self, init_flags: int = 0) -> None:
        status = self.rsmi_init(c_uint64(init_flags))
        if status != 0:
            raise DriverInitError(f"rsmi_init: {self.status_string(status)}")

    def shutdown(self) -> None:
        self.rsmi_shut_down()

    # -- enumeration and identity -----------------------------------------

    def num_devices(self) -> int:
        n = c_uint32(0)
        self._call("rsmi_num_monitor_devices", byref(n))
        return n.value

    def device_name(self, dv_ind: int) -> str:
        buf = create_string_buffer(256)
        self._call("rsmi_dev_name_get", c_uint32(dv_ind), buf, c_size_t(256))
        return buf.value.decode(errors="replace")

    def device_id(self, dv_ind: int) -> str:
        dev = c_uint16(0)
        self._call("rsmi_dev_id_get", c_uint32(dv_ind), byref(dev))
        return f"0x{dev.value:04x}"

    def pci_id(self, dv_ind: int) -> int:
        bdfid = c_uint64(0)
        self._call("rsmi_dev_pci_id_get", c_uint32(dv_ind), byref(bdfid))
        return bdfid.value

    def pci_bus_id(self, dv_ind: int) -> str:
        return bdf_str(self.pci_id(dv_ind))

    def numa_node(self, dv_ind: int) -> int:
        node = c_uint32(0)
        self._call("rsmi_topo_get_numa_node_number", c_uint32(dv_ind), byref(node))
        return node.value

    def cu_num(self, dv_ind: int) -> int:
        cnt = c_int(0)
        self._call("rsmi_dev_cu_num_get", c_uint32(dv_ind), byref(cnt))
        return cnt.value

    # -- memory / power / thermal / clocks ---------------------------------

    def memory_total(self, dv_ind: int) -> int:
        total = c_uint64(0)
        self._call(
            "rsmi_dev_memory_total_get",
            c_uint32(dv_ind),
            c_uint32(RSMI_MEM_TYPE_VRAM),
            byref(total),
        )
        return total.value

    def memory_used(self, dv_ind: int) -> int:
        used = c_uint64(0)
        self._call(
            "rsmi_dev_memory_usage_get",
            c_uint32(dv_ind),
            c_uint32(RSMI_MEM_TYPE_VRAM),
            byref(used),
        )
        return used.value

    def busy_percent(self, dv_ind: int) -> int:
        busy = c_uint32(0)
        self._call("rsmi_dev_busy_percent_get", c_uint32(dv_ind), byref(busy))
        return busy.value

    def power(self, dv_ind: int) -> float:
        watts = c_uint64(0)
        power_type = c_int32(-1)
        try:
            self._call("rsmi_dev_power_get", c_uint32(dv_ind), byref(watts), byref(power_type))
        except RsmiCallError:
            # older path: average power only
            self._call("rsmi_dev_power_ave_get", c_uint32(dv_ind), c_uint32(0), byref(watts))
        return uw_to_w(watts.value)

    def power_cap(self, dv_ind: int) -> float:
        cap = c_uint64(0)
        self._call(
            "rsmi_dev_power_cap_get",
            c_uint32(dv_ind),
            c_uint32(0),
            byref(cap),
        )
        return uw_to_w(cap.value)

    def temperature(self, dv_ind: int, sensor_type: int) -> float:
        mdeg = c_int64(0)
        self._call(
            "rsmi_dev_temp_metric_get",
            c_uint32(dv_ind),
            c_uint32(sensor_type),
            c_uint32(RSMI_TEMP_CURRENT),
            byref(mdeg),
        )
        return mdeg_to_c(mdeg.value)

    def clk_mhz(self, dv_ind: int, clk_type: int) -> float | None:
        freqs = RsmiFrequencies()
        self._call("rsmi_dev_gpu_clk_freq_get", c_uint32(dv_ind), c_uint32(clk_type), byref(freqs))
        if freqs.has_deep_sleep or freqs.num_supported == 0:
            return None
        if freqs.current >= freqs.num_supported:
            return None
        return hz_to_mhz(freqs.frequency[freqs.current])

    # -- Hygon utilization extensions (BLOCKING ~duration_ms) ---------------

    def hcu_util(self, dv_ind: int, duration_ms: int) -> float:
        pct = c_float(0.0)
        self._call("rsmi_dev_hcu_util_get", c_uint32(dv_ind), c_uint32(duration_ms), byref(pct))
        return float(pct.value)

    def cu_util(self, dv_ind: int, duration_ms: int) -> float:
        pct = c_float(0.0)
        self._call("rsmi_dev_cu_util_get", c_uint32(dv_ind), c_uint32(duration_ms), byref(pct))
        return float(pct.value)

    # -- processes ----------------------------------------------------------

    def compute_process_pids(self) -> list[tuple[int, int]]:
        """[(pid, pasid)] for every process the driver knows about."""
        count = c_uint32(0)
        self._call("rsmi_compute_process_info_get", POINTER(RsmiProcessInfo)(), byref(count))
        if count.value == 0:
            return []
        array = (RsmiProcessInfo * count.value)()
        self._call("rsmi_compute_process_info_get", array, byref(count))
        return [(int(p.process_id), int(p.pasid)) for p in array[: count.value]]

    def compute_process_info_v2(self, pid: int) -> dict:
        """Per-PID stats: vram bytes + per-device usage rates."""
        info = RsmiProcessInfoV2()
        self._call("rsmi_compute_process_info_by_pid_get_v2", c_uint32(pid), byref(info))
        used = max(0, int(info.usedGpus))
        return {
            "pid": int(info.processId),
            "vram_bytes": int(info.vramUsageSize),  # BYTES on this build, not MiB
            "vram_rate": float(info.vramUsageRate),
            "gpus": [
                (int(info.gpuIndex[i]), float(info.gpuUsageRate[i]))
                for i in range(min(used, len(info.gpuIndex)))
            ],
        }

    def process_info_by_device(self, pid: int, dv_ind: int) -> dict:
        """Per-(pid, device) stats: vram/sdma bytes + cu occupancy percent.

        Verified on the target: returns the device's real VRAM for the pid
        (equals the v2 total when the pid uses a single device). A pid that
        does NOT use the device also returns success with zeros, so callers
        must only query devices listed in compute_process_info_v2()["gpus"].
        """
        info = RsmiProcessInfo()
        self._call(
            "rsmi_compute_process_info_by_device_get",
            c_uint32(pid),
            c_uint32(dv_ind),
            byref(info),
        )
        return {
            "vram_bytes": int(info.vram_usage),
            "sdma_usage": int(info.sdma_usage),
            "cu_occupancy": float(info.cu_occupancy),
        }

    def dev_proc_usage(self, pid: int, dv_ind: int) -> float:
        pct = c_float(0.0)
        self._call(
            "rsmi_dev_proc_usage_get",
            c_uint32(pid),
            c_uint32(dv_ind),
            byref(pct),
        )
        return float(pct.value)
