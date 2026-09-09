"""NativeBackend: the real implementation on top of librocm_smi64.

Error policy: a driver call failing must never take down monitoring.
Static/metric fields are read one by one; a failed field becomes None
(rendered N/A) while the rest of the device still reports. Errors that
cannot be localized (process list enumeration, windowed utilization) raise
and are handled by the collector.

Utilization semantics: device_metrics().utilization carries the instant
busy_percent as a first-paint fallback; the collector overwrites it (and
cu_utilization) with the windowed hcu_util/cu_util values from
device_util_window, which are the "HCU%"/"CU%" columns hy-smi shows.
"""

from __future__ import annotations

from hytop.backends.base import HCUBackend
from hytop.ffi.errors import DeviceNotFoundError, RsmiCallError
from hytop.ffi.loader import load_driver_library
from hytop.ffi.rsmi import (
    RSMI_CLK_TYPE_MEM,
    RSMI_CLK_TYPE_SYS,
    RSMI_TEMP_TYPE_CORE,
    RSMI_TEMP_TYPE_EDGE,
    RSMI_TEMP_TYPE_JUNCTION,
    RSMI_TEMP_TYPE_MEMORY,
    RsmiApi,
)
from hytop.models.device import DeviceInfo, DeviceMetrics, TemperatureInfo
from hytop.models.process import HcuProcessInfo, ProcessDeviceUsage


class NativeBackend(HCUBackend):
    def __init__(self, rsmi: RsmiApi | None = None):
        # Injectable for tests; lazily loaded for the real driver.
        self._api = rsmi
        self._count = 0
        self._static: dict[int, DeviceInfo] = {}

    def init(self) -> None:
        if self._api is None:
            self._api = RsmiApi(load_driver_library())
        self._api.init()
        self._count = self._api.num_devices()

    def shutdown(self) -> None:
        self._api.shutdown()

    def device_count(self) -> int:
        return self._count

    def _api_or_fail(self):
        if self._api is None:
            raise RsmiCallError(-1, "NativeBackend used before init()")
        return self._api

    def _check_index(self, index: int) -> None:
        if not 0 <= index < self._count:
            raise DeviceNotFoundError(f"device {index} out of range 0..{self._count - 1}")

    @staticmethod
    def _opt(fn):
        """Run one driver read; a failed metric becomes None, not a crash."""
        try:
            return fn()
        except RsmiCallError:
            return None

    # -- identity ----------------------------------------------------------

    def device_info(self, index: int) -> DeviceInfo:
        self._check_index(index)
        api = self._api_or_fail()
        info = DeviceInfo(
            index=index,
            name=self._opt(lambda: api.device_name(index)),
            pci_bus_id=self._opt(lambda: api.pci_bus_id(index)),
            device_id=self._opt(lambda: api.device_id(index)),
            numa_node=self._opt(lambda: api.numa_node(index)),
            memory_total=self._opt(lambda: api.memory_total(index)),
            cu_count=self._opt(lambda: api.cu_num(index)),
        )
        self._static[index] = info
        return info

    def _cached_total(self, index: int) -> int | None:
        info = self._static.get(index)
        if info is None:
            info = self.device_info(index)
        return info.memory_total

    # -- metrics -----------------------------------------------------------

    def device_metrics(self, index: int) -> DeviceMetrics:
        self._check_index(index)
        api = self._api_or_fail()
        return DeviceMetrics(
            index=index,
            utilization=self._opt(lambda: float(api.busy_percent(index))),
            cu_utilization=None,  # filled by the collector from util windows
            memory_used=self._opt(lambda: api.memory_used(index)),
            memory_total=self._cached_total(index),
            temperature=TemperatureInfo(
                edge=self._opt(lambda: api.temperature(index, RSMI_TEMP_TYPE_EDGE)),
                junction=self._opt(lambda: api.temperature(index, RSMI_TEMP_TYPE_JUNCTION)),
                memory=self._opt(lambda: api.temperature(index, RSMI_TEMP_TYPE_MEMORY)),
                core=self._opt(lambda: api.temperature(index, RSMI_TEMP_TYPE_CORE)),
            ),
            power=self._opt(lambda: api.power(index)),
            power_cap=self._opt(lambda: api.power_cap(index)),
            sclk_mhz=self._opt(lambda: api.clk_mhz(index, RSMI_CLK_TYPE_SYS)),
            mclk_mhz=self._opt(lambda: api.clk_mhz(index, RSMI_CLK_TYPE_MEM)),
        )

    def device_util_window(
        self,
        index: int,
        duration_ms: int,
    ) -> tuple[float | None, float | None]:
        self._check_index(index)
        api = self._api_or_fail()
        # Two synchronous windowed reads: blocks ~2 * duration_ms total.
        return (
            api.hcu_util(index, duration_ms),
            api.cu_util(index, duration_ms),
        )

    # -- processes ----------------------------------------------------------

    def processes(self) -> list[HcuProcessInfo]:
        api = self._api_or_fail()
        result = []
        for pid, pasid in api.compute_process_pids():
            proc = HcuProcessInfo(pid=pid, pasid=pasid)
            try:
                v2 = api.compute_process_info_v2(pid)
            except RsmiCallError:
                v2 = None
            if v2 is not None:
                for dev_index, v2_rate in v2["gpus"]:
                    proc.devices[dev_index] = self._process_device_usage(
                        api, pid, dev_index, v2_rate
                    )
            result.append(proc)
        return result

    def _process_device_usage(
        self,
        api: RsmiApi,
        pid: int,
        dev_index: int,
        v2_rate: float,
    ) -> ProcessDeviceUsage:
        usage = ProcessDeviceUsage(device_index=dev_index)
        try:
            info = api.process_info_by_device(pid, dev_index)
        except RsmiCallError:
            info = None
        if info is not None:
            usage.vram_used = info["vram_bytes"]
            usage.sdma_usage = info["sdma_usage"]
            usage.cu_occupancy = info["cu_occupancy"]
        else:
            usage.cu_occupancy = v2_rate
        # rsmi_dev_proc_usage_get is the preferred per-process CU source:
        # verified under load it returns live float percentages while the
        # by_device cu_occupancy stays integer-quantized and laggy and the
        # v2 rate runs coarse.
        try:
            usage.cu_occupancy = api.dev_proc_usage(pid, dev_index)
        except RsmiCallError:
            pass
        return usage

    def process_info(self, pid: int, device_index: int) -> ProcessDeviceUsage | None:
        self._check_index(device_index)
        for proc in self.processes():
            if proc.pid == pid:
                return proc.devices.get(device_index)
        return None
