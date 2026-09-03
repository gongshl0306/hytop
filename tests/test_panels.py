import unittest

from hytop.models.device import DeviceInfo, DeviceMetrics, TemperatureInfo
from hytop.models.process import HcuProcessInfo, ProcessDeviceUsage
from hytop.models.snapshot import SystemSnapshot
from hytop.tui.panels import TuiState, device_lines, handle_key, process_lines, render_frame

GIB = 1024**3


def make_snapshot():
    snapshot = SystemSnapshot(timestamp=100.0)
    for index, used in ((0, 5 * GIB), (1, 8 * GIB)):
        snapshot.device_info[index] = DeviceInfo(
            index=index, name="HYGON DCU-3G", pci_bus_id=f"0000:0{5 + index}:00.0",
            numa_node=index, memory_total=10 * GIB, cu_count=64,
        )
        snapshot.devices[index] = DeviceMetrics(
            index=index,
            utilization=87.5,
            cu_utilization=89.5,
            memory_used=used,
            memory_total=10 * GIB,
            temperature=TemperatureInfo(edge=34.0, junction=39.0, memory=44.0, core=33.0),
            power=162.0,
            power_cap=800.0,
            sclk_mhz=1200.0,
            mclk_mhz=875.0,
        )
    snapshot.processes = [
        HcuProcessInfo(
            pid=200, name="procB", username="root", command="python serv.py",
            cpu_percent=50.0, host_memory=1 * GIB, host_memory_percent=0.5,
            devices={1: ProcessDeviceUsage(device_index=1, vram_used=8 * GIB, cu_occupancy=60.0)},
        ),
        HcuProcessInfo(
            pid=100, name="procA", username="root", command="python train.py",
            cpu_percent=105.0, host_memory=2 * GIB, host_memory_percent=1.0,
            devices={
                0: ProcessDeviceUsage(device_index=0, vram_used=5 * GIB, cu_occupancy=90.0),
                1: ProcessDeviceUsage(device_index=1, vram_used=2 * GIB, cu_occupancy=30.0),
            },
        ),
    ]
    return snapshot


class TestDeviceLines(unittest.TestCase):
    def test_row_content(self):
        lines = device_lines(make_snapshot())
        self.assertIn("Model", lines[0])  # header
        row0 = lines[1]
        self.assertIn("DCU-3G", row0)
        self.assertIn("34.0C", row0)
        self.assertIn("162W", row0)
        self.assertIn("87.5%", row0)
        self.assertIn("89.5%", row0)
        self.assertIn("5.0/10.0G", row0)
        self.assertIn("1200M", row0)
        self.assertIn("875M", row0)

    def test_na_values(self):
        snapshot = make_snapshot()
        snapshot.devices[0].temperature.edge = None
        snapshot.devices[0].power = None
        snapshot.devices[0].mclk_mhz = None
        row = device_lines(snapshot)[1]
        self.assertIn("N/A", row)


class TestProcessLines(unittest.TestCase):
    def test_one_row_per_pid_device_pair(self):
        rows = process_lines(make_snapshot(), TuiState())
        # pid 100 on dev 0 and 1, pid 200 on dev 1 -> 3 rows + header
        self.assertEqual(len(rows), 4)
        self.assertIn("100", rows[1])
        self.assertIn("python train.py", rows[1])

    def test_sort_by_vram_desc(self):
        state = TuiState(process_sort="vram")
        rows = process_lines(make_snapshot(), state)
        self.assertIn("8.0G", rows[1])  # pid 200 dev 1 top
        self.assertIn("200", rows[1])

    def test_sort_by_cpu_desc(self):
        state = TuiState(process_sort="cpu")
        rows = process_lines(make_snapshot(), state)
        self.assertIn("105.0", rows[1])  # pid 100 (cpu 105) first

    def test_filter_devices(self):
        state = TuiState(filter_devices={0})
        rows = process_lines(make_snapshot(), state)
        # only pid100/dev0 remains
        self.assertEqual(len(rows), 2)
        self.assertIn("python train.py", rows[1])
        self.assertNotIn("serv.py", "\n".join(rows))

    def test_selection_marker(self):
        state = TuiState(selected=1)
        rows = process_lines(make_snapshot(), state)
        self.assertTrue(rows[2].startswith(">"))
        self.assertFalse(rows[1].startswith(">"))


class TestRenderFrame(unittest.TestCase):
    def test_full_frame_sections(self):
        frame = render_frame(make_snapshot(), TuiState())
        self.assertIn("hytop 0.1.0", frame[0])
        self.assertIn("devices: 2", frame[0])
        joined = "\n".join(frame)
        self.assertIn("HCU", joined)
        self.assertIn("PID", joined)
        self.assertIn("q quit", joined)

    def test_error_shown_in_frame(self):
        snapshot = make_snapshot()
        snapshot.errors.append("HCU3: boom")
        frame = render_frame(snapshot, TuiState())
        self.assertTrue(any("boom" in line for line in frame))


class TestHandleKey(unittest.TestCase):
    def test_quit(self):
        self.assertEqual(handle_key(TuiState(), ord("q"), 8), "quit")
        self.assertEqual(handle_key(TuiState(), 27, 8), "quit")

    def test_sort_keys(self):
        state = TuiState()
        for key, expected in ((ord("p"), "pid"), (ord("m"), "vram"), (ord("c"), "cu"), (ord("u"), "cpu")):
            handle_key(state, key, 8)
            self.assertEqual(state.process_sort, expected)

    def test_digit_toggles_filter(self):
        import curses

        state = TuiState()
        handle_key(state, ord("3"), 8)
        self.assertEqual(state.filter_devices, {2})
        handle_key(state, ord("4"), 8)
        self.assertEqual(state.filter_devices, {2, 3})
        handle_key(state, ord("3"), 8)
        self.assertEqual(state.filter_devices, {3})
        handle_key(state, ord("4"), 8)
        self.assertIsNone(state.filter_devices)  # empty -> all
        handle_key(state, ord("a"), 8)
        self.assertIsNone(state.filter_devices)
        # digit beyond device count ignored
        handle_key(state, ord("9"), 4)
        self.assertIsNone(state.filter_devices)

    def test_selection_clamps(self):
        import curses

        state = TuiState()
        handle_key(state, curses.KEY_UP, 8)
        self.assertEqual(state.selected, 0)
        handle_key(state, curses.KEY_DOWN, 8)
        self.assertEqual(state.selected, 1)


if __name__ == "__main__":
    unittest.main()
