import curses
import unittest

import dcutop
from dcutop.models.device import DeviceInfo, DeviceMetrics, TemperatureInfo
from dcutop.models.history import DeviceHistory
from dcutop.models.process import HcuProcessInfo, ProcessDeviceUsage
from dcutop.models.snapshot import SystemSnapshot
from dcutop.tui.braille import avg_series, axis_line, braille_chart
from dcutop.tui.panels import (
    DeviceLayout,
    TuiState,
    device_lines,
    handle_key,
    process_lines,
    render_frame,
    text_of,
)
from dcutop.tui.theme import bar_style, power_style, temp_style, util_style

GIB = 1024**3


def make_snapshot(utilization=87.5, power=162.0, edge=34.0, with_history=False):
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
        if with_history:
            hist = DeviceHistory()
            for v in (10.0, 50.0, 90.0):
                hist.append(v, v, used, 100.0)
            snapshot.history[index] = hist
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


LAYOUT = DeviceLayout.for_width(120)


class TestDeviceLayout(unittest.TestCase):
    def test_row_and_header_share_total_width(self):
        header = text_of(LAYOUT.header())
        row = text_of(device_lines(make_snapshot(), LAYOUT)[1])
        self.assertEqual(len(header), len(row))

    def test_adaptive_bars_fill_terminal_width(self):
        for width in (120, 140, 160, 200):
            layout = DeviceLayout.for_width(width)
            header = text_of(layout.header())
            self.assertEqual(len(header), width, f"width {width}")
        self.assertGreater(DeviceLayout.for_width(160).util_bar,
                           DeviceLayout.for_width(120).util_bar)

    def test_minimum_bar_widths_on_narrow_terminal(self):
        layout = DeviceLayout.for_width(60)
        self.assertGreaterEqual(layout.util_bar, 6)
        self.assertGreaterEqual(layout.mem_bar, 6)


class TestDeviceLines(unittest.TestCase):
    def setUp(self):
        self.lines = line_texts(device_lines(make_snapshot(), LAYOUT))

    def test_header_and_row_content(self):
        self.assertIn("HCU%", self.lines[0])
        self.assertIn("VRAM", self.lines[0])
        row0 = self.lines[1]
        self.assertIn("DCU-3G", row0)
        self.assertIn("34.0C", row0)
        self.assertIn("162W", row0)
        self.assertIn("87.5%", row0)
        self.assertIn("89.5%", row0)
        self.assertIn("5.0/10.0G", row0)
        self.assertIn("1200M", row0)
        self.assertIn("875M", row0)
        self.assertIn("█", row0)  # solid blocks, no dither filler
        self.assertNotIn("░", row0)

    def test_na_values(self):
        snapshot = make_snapshot()
        snapshot.devices[0].temperature.edge = None
        snapshot.devices[0].power = None
        snapshot.devices[0].mclk_mhz = None
        row = line_texts(device_lines(snapshot, LAYOUT))[1]
        self.assertIn("N/A", row)

    def test_styles(self):
        lines = device_lines(make_snapshot(edge=80.0, power=760.0, utilization=95.0), LAYOUT)
        styles = {text.strip(): style for text, style in lines[1] if style}
        self.assertEqual(styles.get("80.0C"), "red")
        self.assertEqual(styles.get("760W"), "red")
        self.assertIn("green", styles.values())  # 95% util bar blocks

    def test_cool_device_plain(self):
        # 30% util -> green bar; 50% mem -> green; nothing red/yellow
        lines = device_lines(make_snapshot(utilization=30.0), LAYOUT)
        styles = {s for _, s in lines[1] if s}
        self.assertEqual(styles, {"green"})


class TestBraille(unittest.TestCase):
    def test_chart_padded_to_width(self):
        top, bottom = braille_chart([50.0], 10)
        self.assertEqual(len(top), 10)
        self.assertEqual(len(bottom), 10)

    # one character = one sample, 8 vertical levels (bottom, top):
    GLYPHS = {  # (top, bottom) as braille_chart returns
        12.5: ("\u2800", "\u28c0"),  # level 1: bottom baseline
        25.0: ("\u2800", "\u28f0"),  # level 2
        37.5: ("\u2800", "\u28fc"),  # level 3
        50.0: ("\u2800", "\u28ff"),  # level 4: bottom row full
        62.5: ("\u28c0", "\u28ff"),  # level 5: enters top row
        75.0: ("\u28f0", "\u28ff"),  # level 6
        87.5: ("\u28fc", "\u28ff"),  # level 7
        100.0: ("\u28ff", "\u28ff"),  # level 8: full column
    }

    def test_level_glyphs(self):
        for value, (top, bottom) in self.GLYPHS.items():
            got = braille_chart([value], 1, prefill=False)
            self.assertEqual(got, (top, bottom), f"value {value}")

    def test_wave_translates_one_full_char_per_tick(self):
        # stable shapes: each sample keeps its glyph as the wave scrolls
        top, bottom = braille_chart([100.0, 100.0, 50.0], 3, prefill=False)
        self.assertEqual(top, "\u28ff\u28ff\u2800")
        self.assertEqual(bottom, "\u28ff\u28ff\u28ff")

    def test_zero_value_draws_baseline(self):
        top, bottom = braille_chart([0.0], 1, prefill=False)
        self.assertEqual(top, "\u2800")
        self.assertEqual(bottom, "\u28c0")

    def test_prefill_holds_first_value_across_canvas(self):
        top, bottom = braille_chart([66.0], 10)
        self.assertEqual(bottom, "⣿" * 10)  # 66% -> bottom half full
        self.assertEqual(top, "⣀" * 10)  # level 4 baseline on the top row

    def test_empty_series_stays_blank(self):
        top, bottom = braille_chart([], 5)
        self.assertEqual(top, "⠀" * 5)
        self.assertEqual(bottom, "⠀" * 5)

    def test_axis_line_marks(self):
        line = axis_line(120, interval_s=1.0)
        self.assertIn("|120s", line)
        self.assertIn("|60s", line)
        self.assertIn("|30s", line)
        self.assertLess(line.index("|120s"), line.index("|60s"))
        self.assertLess(line.index("|60s"), line.index("|30s"))

    def test_axis_line_short_span_empty(self):
        self.assertEqual(axis_line(10, interval_s=1.0), "")

    def test_avg_series(self):
        out = avg_series({0: [10.0, 20.0], 1: [30.0, None, 90.0]})
        self.assertEqual(out[0], 20.0)
        self.assertEqual(out[1], 20.0)
        self.assertEqual(out[2], 90.0)


class TestChartSection(unittest.TestCase):
    def test_charts_present_with_cyan_yellow_styles(self):
        from dcutop.tui.panels import chart_lines

        snapshot = make_snapshot(with_history=True)
        lines = chart_lines(snapshot, width=120, interval_s=1.0)
        texts = line_texts(lines)
        self.assertTrue(any("AVG GPU UTL" in t for t in texts))
        self.assertTrue(any("AVG GPU MEM" in t for t in texts))
        styles = {s for line in lines for _, s in line}
        self.assertIn("cyan", styles)
        self.assertIn("yellow", styles)

    def test_host_and_gpu_charts_side_by_side(self):
        from dcutop.tui.panels import chart_lines

        snapshot = make_snapshot(with_history=True)
        snapshot.host_history.append(37.3, 77.2)
        lines = chart_lines(snapshot, width=120, interval_s=1.0)
        texts = line_texts(lines)
        captions = [t for t in texts if ":" in t and ("CPU" in t or "MEM" in t or "UTL" in t)]
        self.assertTrue(any(t.startswith("CPU: 37.3%") for t in captions))
        self.assertTrue(any(t.startswith("MEM: 77.2%") for t in captions))
        self.assertTrue(any("AVG GPU UTL" in t for t in captions))
        self.assertTrue(any("AVG GPU MEM" in t for t in captions))
        # host captions on the LEFT, gpu captions on the RIGHT
        cpu_row = next(t for t in captions if t.startswith("CPU:"))
        utl_row = next(t for t in captions if "AVG GPU UTL" in t)
        self.assertLess(cpu_row.index("CPU:"), utl_row.index("AVG GPU UTL"))
        styles = {sty for line in lines for _, sty in line if sty}
        self.assertEqual({"cyan", "green", "yellow", "magenta", "bold"},
                         styles)

    def test_mem_chart_normalizes_by_total(self):
        from dcutop.tui.panels import chart_lines

        snapshot = make_snapshot(with_history=True)  # 50% / 80% of 10GiB
        lines = chart_lines(snapshot, width=120, interval_s=1.0)
        mem_caption = next(t for t in line_texts(lines) if "AVG GPU MEM" in t)
        self.assertIn("65.0%", mem_caption)  # avg(50, 80)


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
        self.assertIn("bold", [s for _, s in lines[2]])


class TestRenderFrame(unittest.TestCase):
    def test_full_frame_sections(self):
        frame = line_texts(render_frame(make_snapshot(with_history=True), TuiState()))
        joined = "\n".join(frame)
        self.assertIn(f"dcutop {dcutop.__version__}", joined)
        self.assertIn("devices: 2", joined)
        self.assertIn("┌─ Devices ─", joined)
        self.assertIn("┌─ Utilization ─", joined)
        self.assertIn("┌─ Processes ─", joined)
        self.assertIn("AVG GPU UTL", joined)
        self.assertIn("q quit", joined)
        # every box top/bottom border spans the full width
        width = 120
        for line in frame:
            if line.startswith(("┌", "└", "├")):
                self.assertEqual(len(line), width)

    def test_box_rows_are_padded_to_width(self):
        frame = line_texts(render_frame(make_snapshot(), TuiState()))
        width = 120
        for line in frame:
            if line.startswith("│"):
                self.assertEqual(len(line), width, line)

    def test_charts_dropped_on_short_terminal(self):
        tall = render_frame(make_snapshot(with_history=True), TuiState(),
                            height=60)
        short = render_frame(make_snapshot(with_history=True), TuiState(),
                             height=24)
        self.assertTrue(any("AVG GPU UTL" in l for l in line_texts(tall)))
        self.assertFalse(any("AVG GPU UTL" in l for l in line_texts(short)))
        self.assertTrue(any("Processes" in l for l in line_texts(short)))

    def test_error_line_is_red(self):
        snapshot = make_snapshot()
        snapshot.errors.append("HCU3: boom")
        frame = render_frame(snapshot, TuiState())
        error_lines = [line for line in frame if "boom" in text_of(line)]
        self.assertEqual(len(error_lines), 1)
        self.assertIn("red", [s for _, s in error_lines[0]])

    def test_title_is_bold(self):
        frame = render_frame(make_snapshot(), TuiState())
        title_lines = [line for line in frame if f"dcutop {dcutop.__version__}" in text_of(line)]
        self.assertEqual(len(title_lines), 1)
        self.assertIn("bold", [s for _, s in title_lines[0]])


class TestThemeThresholds(unittest.TestCase):
    def test_temp_style(self):
        self.assertIsNone(temp_style(None))
        self.assertIsNone(temp_style(50.0))
        self.assertEqual(temp_style(65.0), "yellow")
        self.assertEqual(temp_style(75.0), "red")

    def test_power_style(self):
        self.assertIsNone(power_style(None, 800.0))
        self.assertIsNone(power_style(600.0, 800.0))  # 75%: plain
        self.assertEqual(power_style(700.0, 800.0), "yellow")  # 87.5%
        self.assertEqual(power_style(720.0, 800.0), "red")  # exactly 90%
        self.assertEqual(power_style(800.0, 800.0), "red")

    def test_util_style(self):
        self.assertIsNone(util_style(None))
        self.assertEqual(util_style(90.0), "green")

    def test_bar_gradient(self):
        self.assertEqual(bar_style(10.0), "green")
        self.assertEqual(bar_style(60.0), "yellow")
        self.assertEqual(bar_style(85.0), "red")
        self.assertIsNone(bar_style(None))


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
