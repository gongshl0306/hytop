import unittest

import hytop


class TestPackage(unittest.TestCase):
    def test_version(self):
        self.assertEqual(hytop.__version__, "0.1.0")

    def test_all_exports_version(self):
        self.assertIn("__version__", hytop.__all__)


if __name__ == "__main__":
    unittest.main()
