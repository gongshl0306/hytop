"""Exception hierarchy for dcutop.

Every error dcutop raises derives from :class:`DcutopError`, so callers can
catch a single base type. Messages are user-facing: they should name the
failed resource and, where useful, how to fix it (e.g. which library paths
were searched) instead of leaking raw OSError text.
"""

from __future__ import annotations


class DcutopError(Exception):
    """Base class for all dcutop errors."""


class DriverNotFoundError(DcutopError):
    """The HCU driver libraries could not be located on this system."""


class DriverInitError(DcutopError):
    """A driver library was found but failed to initialize."""


class DeviceNotFoundError(DcutopError):
    """The requested device index does not exist."""


class MetricNotSupportedError(DcutopError):
    """The driver does not support the requested metric on this device."""


class PermissionDeniedError(DcutopError):
    """The current user lacks permission to query the HCU driver."""


class RsmiCallError(DcutopError):
    """A driver call returned a non-success status.

    Attributes:
        code: raw ``rsmi_status_t`` value from the driver.
    """

    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(message)
