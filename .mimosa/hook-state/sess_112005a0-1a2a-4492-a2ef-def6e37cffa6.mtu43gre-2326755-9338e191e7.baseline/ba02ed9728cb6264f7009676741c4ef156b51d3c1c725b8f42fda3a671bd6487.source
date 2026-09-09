import unittest

from hytop.backends.base import HCUBackend
from hytop.backends.mock import MockBackend


class IncompleteBackend(HCUBackend):
    """Missing every abstract method on purpose."""


class TestBackendProtocol(unittest.TestCase):
    def test_abc_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            HCUBackend()  # type: ignore[abstract]

    def test_incomplete_subclass_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            IncompleteBackend()  # type: ignore[abstract]

    def test_mock_satisfies_protocol(self):
        backend = MockBackend()
        backend.init()
        try:
            self.assertIsInstance(backend, HCUBackend)
            # every protocol entry point is callable
            self.backend_smoke(backend)
        finally:
            backend.shutdown()

    @staticmethod
    def backend_smoke(backend):
        n = backend.device_count()
        for i in range(n):
            backend.device_info(i)
            backend.device_metrics(i)
            backend.device_util_window(i, 10)
        backend.processes()
        backend.process_info(1, 0)


if __name__ == "__main__":
    unittest.main()
