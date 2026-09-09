"""Keep the version consistent across pyproject.toml and dcutop.__version__."""

import pathlib
import re
import unittest

import dcutop


class TestVersionConsistency(unittest.TestCase):
    def test_pyproject_matches_package_version(self):
        pyproject = (
            pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
        ).read_text()
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
        self.assertIsNotNone(match, "pyproject.toml has no version field")
        self.assertEqual(match.group(1), dcutop.__version__)

    def test_console_script_entrypoint_exists(self):
        pyproject = (
            pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
        ).read_text()
        self.assertIn("dcutop = \"dcutop.cli:main\"", pyproject)


if __name__ == "__main__":
    unittest.main()
