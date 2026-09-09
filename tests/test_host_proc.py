import os
import pwd
import unittest

from dcutop.host.proc import (
    CLK_TCK,
    PAGE_SIZE,
    ProcessSampler,
    ProcSample,
    cpu_fields,
    host_cpu_percent,
    host_memory,
    parse_meminfo,
    parse_stat_line,
    proc_cpu_percent,
    sample_process,
    username_for_uid,
)
from tests.proc_fixture import ProcTree, stat_line


class FakeProc(unittest.TestCase):
    """Builds a fixture procfs tree under a temp dir."""

    def setUp(self):
        self.tree = ProcTree()
        self.addCleanup(lambda: None)  # ProcTree cleans itself on exit
        self.root = self.tree.root
        self.now = [1000.0]

    def make_process(self, pid, **kwargs):
        self.tree.make_process(pid, **kwargs)

    def rewrite_stat(self, pid, **kwargs):
        self.tree.rewrite_stat(pid, **kwargs)

    def write_proc_stat(self, total_ticks):
        self.tree.write_proc_stat(total_ticks)

    def write_meminfo(self, **kwargs):
        self.tree.write_meminfo(**kwargs)


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

    def test_cpu_fields(self):
        self.write_proc_stat(1234)
        fields = cpu_fields(self.root)
        self.assertEqual(fields["user"], 1234)
        self.assertEqual(fields["idle"], 0)
        self.assertEqual(len(fields), 10)

    def test_parse_cpu_fields_rejects_non_cpu(self):
        from dcutop.host.proc import parse_cpu_fields

        self.assertIsNone(parse_cpu_fields("cpuX 1 2 3"))
        self.assertIsNone(parse_cpu_fields("garbage"))

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

    @staticmethod
    def fields(**kw):
        from dcutop.host.proc import CPU_FIELD_NAMES

        base = {name: 0 for name in CPU_FIELD_NAMES}
        base.update(kw)
        return base

    def test_host_percent_counts_only_busy_fields(self):
        # 200 busy ticks over 2s on a single core
        expected = 200 / (2.0 * CLK_TCK) * 100
        prev = self.fields(user=1000)
        now = self.fields(user=1200)
        self.assertAlmostEqual(host_cpu_percent(prev, now, 2.0), expected)
        # idle growth alone is NOT busy (the v0.5.0 bug showed ~100% always)
        prev = self.fields(user=1000, idle=50000)
        now = self.fields(user=1000, idle=60000)
        self.assertAlmostEqual(host_cpu_percent(prev, now, 2.0), 0.0)
        self.assertIsNone(host_cpu_percent(None, now, 1.0))
        self.assertIsNone(host_cpu_percent(prev, now, 0.0))

    def test_host_percent_normalized_by_cores(self):
        # 200 busy ticks over 2s across 4 cores: quarter of one core each
        expected = 200 / (2.0 * CLK_TCK * 4) * 100
        prev = self.fields(user=1000)
        now = self.fields(user=1200)
        self.assertAlmostEqual(host_cpu_percent(prev, now, 2.0, ncores=4), expected)
        self.assertIsNone(host_cpu_percent(prev, now, 2.0, ncores=0))  # invalid


class TestCoreCount(FakeProc):
    def test_from_stat_fixture(self):
        from dcutop.host.proc import core_count

        self.write_proc_stat(1000)  # one "cpu " aggregate + one "cpu0" line
        self.assertEqual(core_count(self.root), 1)

    def test_missing_stat_falls_back(self):
        from dcutop.host.proc import core_count
        import os as _os

        self.assertEqual(core_count(self.root), _os.cpu_count() or 1)


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
        self.tree.remove_process(101)
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
