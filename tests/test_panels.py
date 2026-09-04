import curses
import unittest

import hytop
from hytop.models.device import DeviceInfo, DeviceMetrics, TemperatureInfo
from hytop.models.history import DeviceHistory
from hytop.models.process import HcuProcessInfo, ProcessDeviceUsage
from hytop.models.snapshot import SystemSnapshot
from hytop.tui.panels import (
    TuiState,
    bar,
    device_lines,
    handle_key,
    history_lines,
    process_lines,
    render_frame,
    sparkline,
    text_of,
)
from hytop.tui.theme import power_style, temp_style, util_style

GIB = 1024**3


def make_snapshot(utilization=87.5, power=162.0, edge=34.0):
    snapshot = SystemSnapshot(timestamp=100.0)
    for index, used in ((0, 5 * GIB), (1, 8 * GIB)):
        snapshot.device_info[index] = DeviceInfo(
            index=index, name="HYGON DCU-3G", pci_bus_id=f"0000:0{5 + index}:00.0",
            numa_node=index, memory_total=10 * GIB, cu_count=64,
        )
        snapshot.devices[index] = DeviceMetrics(
            index=index,
            utilization=utilization,
            cu_utilization=89.5,
            memory_used=used,
            memory_total=10 * GIB,
            temperature=TemperatureInfo(edge=edge, junction=39.0, memory=44.0, core=33.0),
            power=power,
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


def line_texts(lines):
    return [text_of(line) for line in lines]


class TestBarsAndSparklines(unittest.TestCase):
    def test_bar_levels(self):
        self.assertEqual(bar(None), "[" + "░" * 11 + "]")
        self.assertEqual(bar(0), "[" + "░" * 11 + "]")
        self.assertEqual(bar(100), "[" + "█" * 11 + "]")
        self.assertEqual(bar(50), "[" + "█" * 6 + "░" * 5 + "]")  # round(5.5)=6
        self.assertEqual(bar(200), "[" + "█" * 11 + "]")  # clamped
        self.assertEqual(bar(-5), "[" + "░" * 11 + "]")

    def test_bar_custom_width_and_maximum(self):
        self.assertEqual(bar(500, width=4, maximum=1000), "[" + "██" + "░░" + "]")

    def test_sparkline_levels(self):
        self.assertEqual(sparkline([0, 12.5, 100], 3), "▁▂█")

    def test_sparkline_none_is_lowest(self):
        self.assertEqual(sparkline([None, 100], 2), "▁█")

    def test_sparkline_downsamples_long_series(self):
        self.assertEqual(sparkline([100] * 80, 40), "█" * 40)

    def test_sparkline_empty(self):
        self.assertEqual(sparkline([], 10), "")


class TestHistoryLines(unittest.TestCase):
    def test_history_lines_rendered_two_per_row(self):
        snapshot = make_snapshot()
        for index in (0, 1, 2):
            hist = DeviceHistory()
            for v in (10, 50, 90):
                hist.append(v, v, 100, 100.0)
            snapshot.history[index] = hist
        lines = line_texts(history_lines(snapshot, spark_width=10))
        self.assertEqual(len(lines), 2)  # 3 devices -> 2 rows
        self.assertIn("HCU0:", lines[0])
        self.assertIn("HCU1:", lines[0])
        self.assertIn("HCU2:", lines[1])
        self.assertIn("█", lines[0])

    def test_history_section_empty_without_history(self):
        self.assertEqual(history_lines(make_snapshot()), [])


class TestDeviceLines(unittest.TestCase):
    def test_header_and_row_content(self):
        lines = line_texts(device_lines(make_snapshot()))
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
        self.assertIn("█", row0)  # utilization bar rendered

    def test_na_values(self):
        snapshot = make_snapshot()
        snapshot.devices[0].temperature.edge = None
        snapshot.devices[0].power = None
        snapshot.devices[0].mclk_mhz = None
        row = line_texts(device_lines(snapshot))[1]
        self.assertIn("N/A", row)


class TestDeviceRowStyles(unittest.TestCase):
    def device_row_segments(self, **kwargs):
        lines = device_lines(make_snapshot(**kwargs))
        return lines[1]  # first data row: list of (text, style)

    def seg_styles(self, segments):
        return {text.strip(): style for text, style in segments if style}

    def test_hot_device_red(self):
        segments = self.device_row_segments(edge=80.0)
        styles = self.seg_styles(segments)
        self.assertEqual(styles.get("80.0C"), "red")

    def test_warm_device_yellow(self):
        segments = self.device_row_segments(edge=68.0)
        self.assertEqual(self.seg_styles(segments).get("68.0C"), "yellow")

    def test_cool_device_plain(self):
        segments = self.device_row_segments(edge=34.0)
        self.assertNotIn("34.0C", self.seg_styles(segments))

    def test_power_near_cap_red(self):
        segments = self.device_row_segments(power=760.0)  # 95% of 800W
        self.assertEqual(self.seg_styles(segments).get("760W"), "red")

    def test_power_over_yellow_threshold(self):
        segments = self.device_row_segments(power=660.0)  # 82.5% of 800W
        self.assertEqual(self.seg_styles(segments).get("660W"), "yellow")

    def test_high_utilization_green(self):
        segments = self.device_row_segments(utilization=95.0)
        styles = self.seg_styles(segments)
        colored = {s for s in styles.values() if s == "green"}
        self.assertTrue(colored)


class TestThemeThresholds(unittest.TestCase):
    def test_temp_style(self):
        self.assertIsNone(temp_style(None))
        self.assertIsNone(temp_style(50.0))
        self.assertEqual(temp_style(65.0), "yellow")
        self.assertEqual(temp_style(74.9), "yellow")
        self.assertEqual(temp_style(75.0), "red")

    def test_power_style(self):
        self.assertIsNone(power_style(None, 800.0))
        self.assertIsNone(power_style(100.0, None))
        self.assertIsNone(power_style(100.0, 0))
        self.assertIsNone(power_style(600.0, 800.0))  # 75%: plain
        self.assertEqual(power_style(700.0, 800.0), "yellow")  # 87.5%
        self.assertEqual(power_style(720.0, 800.0), "red")  # exactly 90%: red wins
        self.assertEqual(power_style(800.0, 800.0), "red")

    def test_util_style(self):
        self.assertIsNone(util_style(None))
        self.assertIsNone(util_style(89.9))
        self.assertEqual(util_style(90.0), "green")


class TestProcessLines(unittest.TestCase):
    def test_one_row_per_pid_device_pair(self):
        rows = line_texts(process_lines(make_snapshot(), TuiState()))
        self.assertEqual(len(rows), 4)  # 3 rows + header
        self.assertIn("100", rows[1])
        self.assertIn("python train.py", rows[1])

    def test_sort_by_vram_desc(self):
        state = TuiState(process_sort="vram")
        rows = line_texts(process_lines(make_snapshot(), state))
        self.assertIn("8.0G", rows[1])
        self.assertIn("200", rows[1])

    def test_sort_by_cpu_desc(self):
        state = TuiState(process_sort="cpu")
        rows = line_texts(process_lines(make_snapshot(), state))
        self.assertIn("105.0", rows[1])

    def test_filter_devices(self):
        state = TuiState(filter_devices={0})
        rows = line_texts(process_lines(make_snapshot(), state))
        self.assertEqual(len(rows), 2)
        self.assertIn("python train.py", rows[1])
        self.assertNotIn("serv.py", "\n".join(rows))

    def test_selection_marker_bold(self):
        state = TuiState(selected=1)
        lines = process_lines(make_snapshot(), state)
        self.assertTrue(text_of(lines[2]).startswith(">"))
        selected_styles = [s for _, s in lines[2] if s]
        self.assertIn("bold", selected_styles)
        self.assertEqual(text_of(lines[1]).startswith(">"), False)


class TestRenderFrame(unittest.TestCase):
    def test_full_frame_sections(self):
        frame = line_texts(render_frame(make_snapshot(), TuiState()))
        self.assertIn(f"hytop {hytop.__version__}", frame[0])
        self.assertIn("devices: 2", frame[0])
        joined = "\n".join(frame)
        self.assertIn("HCU", joined)
        self.assertIn("PID", joined)
        self.assertIn("q quit", joined)

    def test_error_line_is_red(self):
        snapshot = make_snapshot()
        snapshot.errors.append("HCU3: boom")
        frame = render_frame(snapshot, TuiState())
        error_lines = [line for line in frame if "boom" in text_of(line)]
        self.assertEqual(len(error_lines), 1)
        self.assertIn("red", [s for _, s in error_lines[0]])

    def test_title_is_bold(self):
        frame = render_frame(make_snapshot(), TuiState())
        self.assertIn("bold", [s for _, s in frame[0]])


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
        handle_key(state, ord("9"), 4)  # beyond device count: ignored
        self.assertIsNone(state.filter_devices)

    def test_selection_clamps(self):
        state = TuiState()
        handle_key(state, curses.KEY_UP, 8)
        self.assertEqual(state.selected, 0)
        handle_key(state, curses.KEY_DOWN, 8)
        self.assertEqual(state.selected, 1)


if __name__ == "__main__":
    unittest.main()
