"""Shared fixture: a fake procfs tree for host-layer tests."""

import os
import shutil
import tempfile


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


class ProcTree:
    """Fake /proc with process dirs, aggregate stat and meminfo."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="hytop-fake-proc-")
        self._cleanup = shutil.rmtree

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.root, ignore_errors=True)

    def make_process(self, pid, comm="python3", cmdline=("python3", "train.py"),
                     utime=10, stime=5, rss_pages=1000, state="S"):
        d = os.path.join(self.root, str(pid))
        os.makedirs(d)
        self.rewrite_stat(pid, comm=comm, state=state, utime=utime,
                          stime=stime, rss_pages=rss_pages)
        if cmdline is not None:
            raw = b"\0".join(part.encode() for part in cmdline) + b"\0"
        else:  # kernel thread: empty cmdline file
            raw = b""
        with open(os.path.join(d, "cmdline"), "wb") as f:
            f.write(raw)

    def rewrite_stat(self, pid, comm="python3", state="S", utime=0, stime=0,
                     rss_pages=1000, nthreads=1):
        with open(os.path.join(self.root, str(pid), "stat"), "w") as f:
            f.write(stat_line(pid, comm, state=state, utime=utime, stime=stime,
                              rss_pages=rss_pages, nthreads=nthreads))

    def remove_process(self, pid):
        shutil.rmtree(os.path.join(self.root, str(pid)))

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
