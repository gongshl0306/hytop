"""Exception hierarchy for hytop.

Every error hytop raises derives from :class:`HytopError`, so callers can
catch a single base type. Messages are user-facing: they should name the
failed resource and, where useful, how to fix it (e.g. which library paths
were searched) instead of leaking raw OSError text.
"""

from __future__ import annotations


class HytopError(Exception):
    """Base class for all hytop errors."""


class DriverNotFoundError(HytopError):
    """The HCU driver libraries could not be located on this system."""


class DriverInitError(HytopError):
    """A driver library was found but failed to initialize."""


class DeviceNotFoundError(HytopError):
    """The requested device index does not exist."""


class MetricNotSupportedError(HytopError):
    """The driver does not support the requested metric on this device."""


class PermissionDeniedError(HytopError):
    """The current user lacks permission to query the HCU driver."""
