import unittest

import dcutop


class TestPackage(unittest.TestCase):
    def test_version_matches_semver(self):
        self.assertRegex(dcutop.__version__, r"^\d+\.\d+\.\d+$")

    def test_all_exports_version(self):
        self.assertIn("__version__", dcutop.__all__)


if __name__ == "__main__":
    unittest.main()
