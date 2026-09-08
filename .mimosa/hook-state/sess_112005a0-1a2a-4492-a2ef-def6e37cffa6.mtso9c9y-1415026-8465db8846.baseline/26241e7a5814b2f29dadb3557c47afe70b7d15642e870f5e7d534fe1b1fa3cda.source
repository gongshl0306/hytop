"""Locate and load the HCU driver libraries.

Search order (first hit wins):

1. directories in ``$HYTOP_LIBRARY_PATH`` (colon separated)
2. ``/opt/hyhal/lib``  — where the HCU driver stack installs by default
3. ``/opt/dtk/lib``    — older DTK layouts
4. bare soname via the dynamic linker cache (``ctypes.CDLL("librocm_smi64.so")``)

Failure raises :class:`DriverNotFoundError` with the full list of searched
paths and actionable hints — never a bare ``OSError``.
"""

from __future__ import annotations

import ctypes
import os

from hytop.ffi.errors import DriverNotFoundError

RSMI_LIBRARY = "librocm_smi64.so"

DEFAULT_DIRS = ("/opt/hyhal/lib", "/opt/dtk/lib")


def candidate_dirs() -> list[str]:
    dirs: list[str] = []
    env = os.environ.get("HYTOP_LIBRARY_PATH", "")
    dirs.extend(p for p in env.split(":") if p)
    dirs.extend(d for d in DEFAULT_DIRS if d not in dirs)
    return dirs


def search_candidates(names: list[str], dirs: list[str]) -> str | None:
    """First existing library path among dirs/names, else None."""
    for d in dirs:
        for name in names:
            path = os.path.join(d, name)
            if os.path.exists(path):
                return path
    return None


def load_driver_library(names: list[str] | None = None) -> ctypes.CDLL:
    names = names if names is not None else [RSMI_LIBRARY]
    dirs = candidate_dirs()
    searched = [os.path.join(d, n) for d in dirs for n in names]

    path = search_candidates(names, dirs)
    if path is not None:
        return ctypes.CDLL(path)

    # last resort: let the dynamic linker resolve the bare soname
    for name in names:
        searched.append(name)
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue

    raise DriverNotFoundError(
        "HCU driver libraries not found.\n"
        "Searched:\n"
        + "".join(f"  {p}\n" for p in searched)
        + "Check:\n"
        "  - `hy-smi` works and /opt/hyhal/lib exists on this machine\n"
        "  - or point HYTOP_LIBRARY_PATH at the directory holding "
        + ", ".join(names)
    )
