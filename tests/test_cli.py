import contextlib
import io
import unittest

import dcutop
from dcutop.cli import main, parse_device_list
from dcutop.ffi.errors import DriverNotFoundError


def run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class TestParseDeviceList(unittest.TestCase):
    def test_none_means_all(self):
        self.assertEqual(parse_device_list(None, 8), list(range(8)))

    def test_single_and_multiple(self):
        self.assertEqual(parse_device_list("0", 8), [0])
        self.assertEqual(parse_device_list("0,3,7", 8), [0, 3, 7])

    def test_sorted_and_deduped(self):
        self.assertEqual(parse_device_list("3,0,3", 8), [0, 3])

    def test_empty_parts_ignored(self):
        self.assertEqual(parse_device_list("0,,1,", 8), [0, 1])

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            parse_device_list("8", 8)
        with self.assertRaises(ValueError):
            parse_device_list("-1", 8)

    def test_not_an_integer(self):
        with self.assertRaises(ValueError):
            parse_device_list("0,x", 8)


class TestOnceOutput(unittest.TestCase):
    def test_mock_once_table(self):
        code, out, err = run_main(["--once", "--backend", "mock", "--window-ms", "10"])
        self.assertEqual(code, 0)
        self.assertIn(f"dcutop {dcutop.__version__}", out)
        self.assertIn("HCU", out)
        self.assertIn("Model", out)
        rows = [line for line in out.splitlines() if "MOCK DCU-1" in line]
        self.assertEqual(len(rows), 8)  # all devices
        self.assertIn("10001", out)  # mock process pids
        self.assertIn("10002", out)
        # processes section
        self.assertIn("COMMAND", out)
        self.assertIn("mocktrain", out)

    def test_device_filter(self):
        code, out, _ = run_main(
            ["--once", "--backend", "mock", "--window-ms", "10", "-d", "0,3"]
        )
        self.assertEqual(code, 0)
        rows = [line for line in out.splitlines() if "MOCK DCU-1" in line]
        self.assertEqual(len(rows), 2)
        self.assertTrue(any(line.strip().startswith("0 ") for line in rows))
        self.assertTrue(any(line.strip().startswith("3 ") for line in rows))

    def test_na_for_missing_values(self):
        code, out, _ = run_main(["--once", "--backend", "mock", "--window-ms", "10"])
        self.assertEqual(code, 0)
        self.assertIn("N/A", out)  # mock procs have no CPU% without /proc


class TestCliErrors(unittest.TestCase):
    def test_driver_not_found_is_actionable(self):
        def failing_factory(name):
            raise DriverNotFoundError(
                "HCU driver libraries not found.\nSearched:\n"
                "  /opt/hyhal/lib/librocm_smi64.so\nCheck:\n  set DCUTOP_LIBRARY_PATH"
            )

        out, err = io.StringIO(), io.StringIO()
        code = main(["--once"], backend_factory=failing_factory, stdout=out, stderr=err)
        self.assertEqual(code, 2)
        self.assertIn("DCUTOP_LIBRARY_PATH", err.getvalue())
        self.assertIn("/opt/hyhal/lib/librocm_smi64.so", err.getvalue())

    def test_invalid_device_list(self):
        code, _, err = run_main(["--once", "--backend", "mock", "-d", "abc"])
        self.assertEqual(code, 2)
        self.assertIn("--device", err)

        code, _, err = run_main(["--once", "--backend", "mock", "-d", "99"])
        self.assertEqual(code, 2)
        self.assertIn("out of range", err)

    def test_invalid_interval(self):
        code, _, err = run_main(["--interval", "0"])
        self.assertEqual(code, 2)
        self.assertIn("--interval", err)

    def test_json_schema(self):
        import json as json_module

        code, out, err = run_main(
            ["--json", "--backend", "mock", "--window-ms", "10"]
        )
        self.assertEqual(code, 0)
        payload = json_module.loads(out)
        self.assertEqual(payload["dcutop_version"], dcutop.__version__)
        self.assertIn("timestamp", payload)
        self.assertEqual(len(payload["devices"]), 8)
        dev = payload["devices"][0]
        for key in (
            "index", "name", "utilization", "cu_utilization", "memory_used",
            "memory_total", "temperature", "power", "power_cap", "sclk_mhz",
        ):
            self.assertIn(key, dev)
        self.assertEqual(sorted(dev["temperature"]), ["core", "edge", "junction", "memory"])
        self.assertGreater(len(payload["processes"]), 0)
        proc = payload["processes"][0]
        for key in ("pid", "username", "command", "devices", "cpu_percent"):
            self.assertIn(key, proc)
        # JSON object keys must be strings
        for dev_key in proc["devices"]:
            self.assertIsInstance(dev_key, str)
        self.assertIn("errors", payload)
        self.assertIn("host", payload)

    def test_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as ctx:
                main(["--version"], stdout=io.StringIO(), stderr=io.StringIO())
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn(dcutop.__version__, out.getvalue())


if __name__ == "__main__":
    unittest.main()
