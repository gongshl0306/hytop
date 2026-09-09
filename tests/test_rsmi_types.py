import ctypes
import unittest

from dcutop.ffi.errors import RsmiCallError
from dcutop.ffi.rsmi import (
    RSMI_CLK_TYPE_MEM,
    RSMI_CLK_TYPE_SYS,
    RSMI_MAX_NUM_FREQUENCIES,
    RSMI_TEMP_TYPE_CORE,
    RSMI_TEMP_TYPE_EDGE,
    RSMI_TEMP_TYPE_JUNCTION,
    RSMI_TEMP_TYPE_MEMORY,
    RsmiFrequencies,
    RsmiProcessInfo,
    RsmiProcessInfoV2,
    bdf_str,
    hz_to_mhz,
    mdeg_to_c,
    uw_to_w,
)


class TestStructLayouts(unittest.TestCase):
    """Sizes measured on the target (librocm_smi64.so.2.8).

    A wrong layout here hands the driver a short buffer — silent memory
    corruption, so these asserts are the regression fence.
    """

    def test_frequencies_struct_is_280(self):
        # RSMI_MAX_NUM_FREQUENCIES is 33 (32 + sleep slot), NOT 32.
        self.assertEqual(RSMI_MAX_NUM_FREQUENCIES, 33)
        self.assertEqual(ctypes.sizeof(RsmiFrequencies), 280)

    def test_process_info_v1_is_32(self):
        self.assertEqual(ctypes.sizeof(RsmiProcessInfo), 32)

    def test_process_info_v2_is_152(self):
        self.assertEqual(ctypes.sizeof(RsmiProcessInfoV2), 152)

    def test_v2_field_offsets(self):
        self.assertEqual(RsmiProcessInfoV2.gpuIndex.offset, 24)
        self.assertEqual(RsmiProcessInfoV2.gpuUsageRate.offset, 88)

    def test_v1_field_offsets(self):
        self.assertEqual(RsmiProcessInfo.vram_usage.offset, 8)
        self.assertEqual(RsmiProcessInfo.sdma_usage.offset, 16)

    def test_enum_constants(self):
        self.assertEqual(RSMI_TEMP_TYPE_EDGE, 0)
        self.assertEqual(RSMI_TEMP_TYPE_JUNCTION, 1)
        self.assertEqual(RSMI_TEMP_TYPE_MEMORY, 2)
        self.assertEqual(RSMI_TEMP_TYPE_CORE, 11)
        self.assertEqual(RSMI_CLK_TYPE_SYS, 0)
        self.assertEqual(RSMI_CLK_TYPE_MEM, 4)


class TestUnitConversions(unittest.TestCase):
    def test_millidegrees_to_celsius(self):
        self.assertEqual(mdeg_to_c(31000), 31.0)
        self.assertEqual(mdeg_to_c(42500), 42.5)

    def test_microwatts_to_watts(self):
        self.assertEqual(uw_to_w(162_000_000), 162.0)
        self.assertEqual(uw_to_w(800_000_000), 800.0)

    def test_herz_to_mhz(self):
        self.assertEqual(hz_to_mhz(1_200_000_000), 1200.0)
        self.assertEqual(hz_to_mhz(875_000_000), 875.0)

    def test_none_passthrough(self):
        self.assertIsNone(mdeg_to_c(None))
        self.assertIsNone(uw_to_w(None))
        self.assertIsNone(hz_to_mhz(None))


class TestBdfString(unittest.TestCase):
    def test_real_value_from_target(self):
        # Smoke test saw raw 0x500 for the device lspci calls 05:00.0.
        self.assertEqual(bdf_str(0x500), "0000:05:00.0")

    def test_another_bus(self):
        self.assertEqual(bdf_str(0x3600), "0000:36:00.0")

    def test_full_encoding(self):
        raw = (0x0002 << 3) | 0x1 | (0x88 << 8)  # func=1 dev=2 bus=0x88
        self.assertEqual(bdf_str(raw), "0000:88:02.1")

    def test_domain_encoding(self):
        raw = (1 << 32) | (5 << 8)
        self.assertEqual(bdf_str(raw), "0001:05:00.0")

    def test_none_passthrough(self):
        self.assertIsNone(bdf_str(None))


class TestRsmiCallError(unittest.TestCase):
    def test_carries_code_and_message(self):
        err = RsmiCallError(7, "rsmi_dev_power_get: unknown rsmi status 7")
        self.assertEqual(err.code, 7)
        self.assertEqual(str(err), "rsmi_dev_power_get: unknown rsmi status 7")

    def test_is_dcutop_error(self):
        from dcutop.ffi.errors import DcutopError

        self.assertTrue(issubclass(RsmiCallError, DcutopError))


if __name__ == "__main__":
    unittest.main()
