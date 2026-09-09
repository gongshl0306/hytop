import unittest

import hytop


class TestPackage(unittest.TestCase):
    def test_version_matches_semver(self):
        self.assertRegex(hytop.__version__, r"^\d+\.\d+\.\d+$")

    def test_all_exports_version(self):
        self.assertIn("__version__", hytop.__all__)


if __name__ == "__main__":
    unittest.main()
