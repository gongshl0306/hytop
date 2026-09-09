import unittest

from dcutop.ffi.errors import (
    DeviceNotFoundError,
    DriverInitError,
    DriverNotFoundError,
    DcutopError,
    MetricNotSupportedError,
    PermissionDeniedError,
)

SUBCLASSES = [
    DriverNotFoundError,
    DriverInitError,
    DeviceNotFoundError,
    MetricNotSupportedError,
    PermissionDeniedError,
]


class TestErrorHierarchy(unittest.TestCase):
    def test_all_derive_from_dcutop_error(self):
        for exc in SUBCLASSES:
            self.assertTrue(issubclass(exc, DcutopError), exc.__name__)

    def test_base_derives_from_exception(self):
        self.assertTrue(issubclass(DcutopError, Exception))

    def test_catch_via_base_class(self):
        with self.assertRaises(DcutopError):
            raise DriverNotFoundError("librocm_smi64.so not found")

    def test_message_preserved(self):
        err = MetricNotSupportedError("power_cap not supported on this device")
        self.assertEqual(str(err), "power_cap not supported on this device")

    def test_each_is_concrete_and_raisable(self):
        for exc_type in SUBCLASSES:
            err = exc_type("boom")
            self.assertIsInstance(err, DcutopError)
            self.assertEqual(str(err), "boom")


if __name__ == "__main__":
    unittest.main()
