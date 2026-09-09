import os
import pwd
import unittest

from dcutop.backends.mock import MockBackend
from dcutop.host.proc import ProcessSampler
from dcutop.host.process import attach_host_info
from tests.proc_fixture import ProcTree


def pwd_username():
    return pwd.getpwuid(os.getuid()).pw_name


class TestAttachHostInfo(unittest.TestCase):
    def test_fills_host_fields_from_proc(self):
        with ProcTree() as tree:
            tree.make_process(10001, comm="mocktrain", cmdline=("python", "train.py", "--epochs", "9"),
                              utime=10, stime=0, rss_pages=1000)
            tree.write_meminfo(total_kib=1_000_000)
            procs = MockBackend().processes()  # includes pid 10001
            clock_now = [42.0]
            sampler = ProcessSampler(root=tree.root, clock=lambda: clock_now[0])
            # pre-warm so CPU% is available on the attach refresh
            sampler.refresh([p.pid for p in procs])
            tree.rewrite_stat(10001, utime=110, stime=0)
            clock_now[0] = 44.0  # 2s of wall time for the delta

            attach_host_info(procs, sampler, proc_root=tree.root)

            proc = next(p for p in procs if p.pid == 10001)
            self.assertEqual(proc.username, pwd_username())
            self.assertEqual(proc.command, "python train.py --epochs 9")
            # /proc comm wins for `name`: the real driver provides none
            self.assertEqual(proc.name, "python3")
            self.assertEqual(proc.host_memory, 1000 * os.sysconf("SC_PAGE_SIZE"))
            self.assertAlmostEqual(
                proc.host_memory_percent,
                1000 * os.sysconf("SC_PAGE_SIZE") / (1_000_000 * 1024) * 100.0,
            )
            self.assertIsNotNone(proc.cpu_percent)  # second sample available
            # device-side fields untouched
            self.assertIn(0, proc.devices)
            self.assertIsNotNone(proc.devices[0].vram_used)

    def test_exited_process_keeps_device_info_without_host_fields(self):
        with ProcTree() as tree:
            procs = MockBackend().processes()
            procs = [p for p in procs if p.pid == 10002]  # not in /proc tree
            sampler = ProcessSampler(root=tree.root, clock=lambda: 42.0)
            attach_host_info(procs, sampler, proc_root=tree.root)
            proc = procs[0]
            self.assertIsNone(proc.username)
            self.assertIsNone(proc.command)
            self.assertIsNone(proc.cpu_percent)
            self.assertIn(3, proc.devices)  # device info intact

    def test_mem_total_passed_explicitly(self):
        with ProcTree() as tree:
            procs = MockBackend().processes()
            sampler = ProcessSampler(root=tree.root, clock=lambda: 42.0)
            attach_host_info(procs, sampler, mem_total=2 * 1024**3, proc_root=tree.root)
            proc = procs[0]
            # no /proc entry: nothing attached; but call must not crash


if __name__ == "__main__":
    unittest.main()
