import unittest

from dcutop.tui.formatter import (
    NA,
    fmt_bytes,
    fmt_clock,
    fmt_mem_pair,
    fmt_percent,
    fmt_power,
    fmt_temp,
    truncate,
)


class TestFormatter(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual(fmt_bytes(None), NA)
        self.assertEqual(fmt_bytes(5 * 1024**3), "5.0G")
        self.assertEqual(fmt_bytes(512 * 1024**2), "512.0M")
        self.assertEqual(fmt_bytes(2 * 1024**4), "2.0T")
        self.assertEqual(fmt_bytes(100), "100B")

    def test_mem_pair_scales_to_total(self):
        self.assertEqual(fmt_mem_pair(None, None), NA)
        self.assertEqual(fmt_mem_pair(5 * 1024**3, 10 * 1024**3), "5.0/10.0G")
        self.assertEqual(fmt_mem_pair(None, 10 * 1024**3), "N/A/10.0G")
        self.assertEqual(fmt_mem_pair(512 * 1024**2, 1024**3), "0.5/1.0G")  # shared unit
        self.assertEqual(fmt_mem_pair(5 * 1024**3, None), "5.0G/N/A")

    def test_percent_temp_power_clock(self):
        self.assertEqual(fmt_percent(None), NA)
        self.assertEqual(fmt_percent(96.04), "96.0%")
        self.assertEqual(fmt_percent(96.04, precision=0), "96%")
        self.assertEqual(fmt_temp(None), NA)
        self.assertEqual(fmt_temp(34.02), "34.0C")
        self.assertEqual(fmt_power(None), NA)
        self.assertEqual(fmt_power(162.4), "162W")
        self.assertEqual(fmt_clock(None), NA)
        self.assertEqual(fmt_clock(1200.0), "1200M")

    def test_truncate(self):
        self.assertEqual(truncate(None, 5), NA)
        self.assertEqual(truncate("abc", 5), "abc")
        self.assertEqual(len(truncate("abcdefgh", 5)), 5)
        self.assertEqual(truncate("abcdef", 5), "abcd…")


if __name__ == "__main__":
    unittest.main()
