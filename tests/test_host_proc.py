import os
import pwd
import shutil
import tempfile
import unittest

from hytop.host.proc import (
    CLK_TCK,
    PAGE_SIZE,
    ProcessSampler,
    ProcSample,
    cpu_total_ticks,
    host_cpu_percent,
    host_memory,
    parse_cpu_total,
    parse_meminfo,
    parse_stat_line,
    proc_cpu_percent,
    sample_process,
    username_for_uid,
)


def stat_line(pid, comm, state="S", utime=0, stime=0, rss_pages=100, nthreads=1):
    # after "pid (comm) ", rest[0]=field3(state), rest[11]=utime(f14),
    # rest[12]=stime(f15), rest[17]=num_threads(f20), rest[21]=rss(f24)
    rest = ["0"] * 50
    rest[0] = state
    rest[11] = str(utime)
    rest[12] = str(stime)
    rest[17] = str(nthreads)
    rest[21] = str(rss_pages)
    return f"{pid} ({comm}) " + " ".join(rest)


class FakeProc(unittest.TestCase):
    """Builds a fixture procfs tree under a temp dir."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="hytop-fake-proc-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.now = [1000.0]

    def make_process(self, pid, comm="python3", cmdline=("python3", "train.py"),
                     utime=10, stime=5, rss_pages=1000, state="S"):
        d = os.path.join(self.root, str(pid))
        os.makedirs(d)
        with open(os.path.join(d, "stat"), "w") as f:
            f.write(stat_line(pid, comm, state=state, utime=utime, stime=stime, rss_pages=rss_pages))
        if cmdline is not None:
            raw = b"\0".join(part.encode() for part in cmdline) + b"\0"
            with open(os.path.join(d, "cmdline"), "wb") as f:
                f.write(raw)
        else:  # kernel thread: empty cmdline file
            with open(os.path.join(d, "cmdline"), "wb") as f:
                f.write(b"")

    def rewrite_stat(self, pid, **kwargs):
        d = os.path.join(self.root, str(pid))
        comm = kwargs.pop("comm", "python3")
        with open(os.path.join(d, "stat"), "w") as f:
            f.write(stat_line(pid, comm, **kwargs))

    def write_proc_stat(self, total_ticks):
        with open(os.path.join(self.root, "stat"), "w") as f:
            f.write(f"cpu  {total_ticks} 0 0 0 0 0 0 0 0 0\n")
            f.write("cpu0 500 0 0 0 0 0 0 0 0 0\n")

    def write_meminfo(self, total_kib=1_000_000, avail_kib=250_000):
        with open(os.path.join(self.root, "meminfo"), "w") as f:
            f.write(f"MemTotal:       {total_kib} kB\n")
            f.write(f"MemFree:        {avail_kib // 2} kB\n")
            f.write(f"MemAvailable:   {avail_kib} kB\n")
            f.write("SwapTotal:      0 kB\n")


class TestParseStatLine(FakeProc):
    def test_simple_comm(self):
        pid, comm, state, utime, stime, rss = parse_stat_line(
            stat_line(68259, "python3", utime=100, stime=20, rss_pages=512)
        )
        self.assertEqual((pid, comm, state), (68259, "python3", "S"))
        self.assertEqual((utime, stime), (100.0, 20.0))
        self.assertEqual(rss, 512)

    def test_comm_with_spaces_and_parens(self):
        pid, comm, state, _, _, _ = parse_stat_line(
            stat_line(7, "weird (na me) proc")
        )
        self.assertEqual(comm, "weird (na me) proc")
        self.assertEqual(pid, 7)


class TestSampleProcess(FakeProc):
    def test_full_sample(self):
        self.make_process(100, utime=10, stime=5, rss_pages=1000)
        s = sample_process(self.root, 100)
        self.assertEqual(s.pid, 100)
        self.assertEqual(s.uid, os.getuid())  # fixture dir owned by us
        self.assertEqual(s.name, "python3")
        self.assertEqual(s.command, "python3 train.py")
        self.assertEqual(s.rss_bytes, 1000 * PAGE_SIZE)
        self.assertEqual(s.cpu_ticks, 15.0)

    def test_kernel_thread_gets_bracketed_comm(self):
        self.make_process(11, comm="kworker/0:1", cmdline=None)
        s = sample_process(self.root, 11)
        self.assertEqual(s.command, "[kworker/0:1]")

    def test_missing_process_returns_none(self):
        self.assertIsNone(sample_process(self.root, 999))

    def test_zombie_still_sampled(self):
        self.make_process(12, state="Z")
        self.assertEqual(sample_process(self.root, 12).state, "Z")


class TestParsers(FakeProc):
    def test_meminfo_to_bytes(self):
        self.write_meminfo(total_kib=1_000_000, avail_kib=250_000)
        total, avail = host_memory(self.root)
        self.assertEqual(total, 1_000_000 * 1024)
        self.assertEqual(avail, 250_000 * 1024)

    def test_cpu_total(self):
        self.write_proc_stat(1234)
        self.assertEqual(cpu_total_ticks(self.root), 1234 + 500 * 0)  # aggregate line only
        # note: aggregate line is the fixture's first "cpu " line

    def test_parse_cpu_total_rejects_non_cpu(self):
        self.assertIsNone(parse_cpu_total("cpuX 1 2 3"))
        self.assertIsNone(parse_cpu_total("garbage"))

    def test_host_memory_missing_file(self):
        self.assertIsNone(host_memory(self.root))


class TestCpuMath(unittest.TestCase):
    @staticmethod
    def sample(ticks, monotonic):
        return ProcSample(pid=1, uid=0, state="S", name="x", command="x",
                          rss_bytes=0, cpu_ticks=ticks, monotonic=monotonic)

    def test_process_percent(self):
        # 100 ticks over 2.0s wall at CLK_TCK: 100 / (2 * CLK_TCK) * 100
        expected = 100 / (2.0 * CLK_TCK) * 100
        self.assertAlmostEqual(
            proc_cpu_percent(self.sample(10, 1000.0), self.sample(110, 1002.0)),
            expected,
        )

    def test_process_percent_none_cases(self):
        self.assertIsNone(proc_cpu_percent(None, self.sample(10, 1.0)))
        self.assertIsNone(proc_cpu_percent(self.sample(10, 1.0), None))
        self.assertIsNone(proc_cpu_percent(self.sample(10, 5.0), self.sample(20, 5.0)))  # no wall

    def test_process_percent_clamps_negative(self):
        self.assertEqual(
            proc_cpu_percent(self.sample(100, 1.0), self.sample(50, 2.0)), 0.0
        )

    def test_host_percent(self):
        # 200 ticks over 2s: 100% of one core-equivalent of total capacity
        expected = 200 / (2.0 * CLK_TCK) * 100
        self.assertAlmostEqual(host_cpu_percent(1000, 1200, 2.0), expected)
        self.assertIsNone(host_cpu_percent(None, 10, 1.0))
        self.assertIsNone(host_cpu_percent(0, 10, 0.0))


class TestProcessSampler(FakeProc):
    def sampler(self):
        return ProcessSampler(root=self.root, clock=lambda: self.now[0])

    def test_first_refresh_has_no_cpu_percent(self):
        self.make_process(100)
        self.write_proc_stat(1000)
        s = self.sampler()
        s.refresh([100])
        self.assertIsNone(s.cpu_percent(100))
        self.assertIsNone(s.host_cpu_percent())

    def test_second_refresh_computes_cpu_percent(self):
        self.make_process(100, utime=10, stime=0)
        self.write_proc_stat(1000)
        s = self.sampler()
        s.refresh([100])

        self.rewrite_stat(100, utime=110, stime=0)  # +100 ticks
        self.write_proc_stat(1200)  # +200 ticks host-wide
        self.now[0] = 1002.0  # 2s wall
        s.refresh([100])

        expected = 100 / (2.0 * CLK_TCK) * 100
        self.assertAlmostEqual(s.cpu_percent(100), expected)
        self.assertAlmostEqual(s.host_cpu_percent(), 200 / (2.0 * CLK_TCK) * 100)

    def test_vanished_pid_dropped(self):
        self.make_process(100)
        self.make_process(101)
        s = self.sampler()
        s.refresh([100, 101])
        shutil.rmtree(os.path.join(self.root, "101"))
        s.refresh([100, 101])
        self.assertIn(100, s._prev)
        self.assertNotIn(101, s._prev)


class TestUsername(unittest.TestCase):
    def test_current_user(self):
        self.assertEqual(username_for_uid(os.getuid()), pwd.getpwuid(os.getuid()).pw_name)

    def test_unknown_uid_falls_back_to_number(self):
        self.assertEqual(username_for_uid(99999999), "99999999")


if __name__ == "__main__":
    unittest.main()
