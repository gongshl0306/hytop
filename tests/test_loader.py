import os
import tempfile
import unittest
from unittest import mock

from dcutop.ffi.errors import DriverNotFoundError
from dcutop.ffi.loader import DEFAULT_DIRS, candidate_dirs, load_driver_library, search_candidates


class TestCandidateDirs(unittest.TestCase):
    def test_default_dirs_without_env(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(candidate_dirs(), list(DEFAULT_DIRS))

    def test_env_prepends_and_dedups(self):
        env = {"DCUTOP_LIBRARY_PATH": "/custom/a:/custom/b"}
        with mock.patch.dict(os.environ, env, clear=True):
            dirs = candidate_dirs()
        self.assertEqual(dirs, ["/custom/a", "/custom/b", *DEFAULT_DIRS])

    def test_env_colon_separated_and_empty_segments_ignored(self):
        env = {"DCUTOP_LIBRARY_PATH": "/x::/y:"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(candidate_dirs()[0], "/x")
            self.assertIn("/y", candidate_dirs())


class TestSearchCandidates(unittest.TestCase):
    def test_returns_first_existing(self):
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            fake = Path(d2) / "librocm_smi64.so"
            fake.write_text("")
            hit = search_candidates(["librocm_smi64.so"], [d1, d2])
            self.assertEqual(hit, str(fake))

    def test_none_when_missing_everywhere(self):
        self.assertIsNone(search_candidates(["libnope.so"], ["/no/such/dir"]))


class TestLoadDriverLibrary(unittest.TestCase):
    def test_missing_library_message_is_actionable(self):
        # A name that cannot exist anywhere: machine-independent failure path.
        with self.assertRaises(DriverNotFoundError) as ctx:
            load_driver_library(names=["libdefinitely_not_dcutop_xyz.so"])
        msg = str(ctx.exception)
        self.assertIn("HCU driver libraries not found", msg)
        self.assertIn(os.path.join("/opt/hyhal/lib", "libdefinitely_not_dcutop_xyz.so"), msg)
        self.assertIn("DCUTOP_LIBRARY_PATH", msg)
        self.assertIn("hy-smi", msg)

    def test_real_library_loads_where_present(self):
        try:
            lib = load_driver_library()
        except DriverNotFoundError:
            self.skipTest("no HCU driver on this machine")
        self.assertTrue(hasattr(lib, "rsmi_init"))


if __name__ == "__main__":
    unittest.main()
