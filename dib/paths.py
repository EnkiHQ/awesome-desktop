"""Runtime state lives under the Windows-provided user temporary directory."""
from __future__ import annotations

import ctypes
from pathlib import Path

# Deliberately distinct from the sibling DesktopBounce runtime directory.
RUNTIME_DIRECTORY_NAME = 'DesktopIconBilliards'


def _temporary_directory() -> Path:
    """Return the Windows per-user temporary directory."""
    get_temp_path = ctypes.windll.kernel32.GetTempPathW
    get_temp_path.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p]
    get_temp_path.restype = ctypes.c_uint32
    size = 260
    while True:
        buffer = ctypes.create_unicode_buffer(size)
        length = get_temp_path(size, buffer)
        if not length:
            raise ctypes.WinError()
        if length < size:
            break
        # The buffer was too small; retry with the required length.
        size = length + 1
    return Path(buffer.value)


def runtime_directory() -> Path:
    """Return the per-user directory for journals and logs, creating it if needed."""
    directory = _temporary_directory() / RUNTIME_DIRECTORY_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory
