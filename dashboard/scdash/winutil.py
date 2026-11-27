"""Every Windows-only call, each with a harmless fallback elsewhere.

Stage 1 needs one: opening the game's log so that the game can still write, truncate, rename or
delete it while we read. Python's own open() shares read and write on Windows but not delete
(PLAN §8). The game empties Game.log in place at each launch in this build, so nothing deletes it
today, but a patch could change that, and a reader must never be the reason it fails.
"""
import os
import sys

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    # A private kernel32 instance, so setting argtypes here cannot disturb other ctypes users.
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _CreateFileW = _kernel32.CreateFileW
    _CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                             wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _CreateFileW.restype = wintypes.HANDLE
    _CloseHandle = _kernel32.CloseHandle
    _CloseHandle.argtypes = [wintypes.HANDLE]
    _CloseHandle.restype = wintypes.BOOL

    _GENERIC_READ = 0x80000000
    _FILE_SHARE_ALL = 0x1 | 0x2 | 0x4          # read, write, delete
    _OPEN_EXISTING = 3
    _FILE_ATTRIBUTE_NORMAL = 0x80
    _INVALID_HANDLE = wintypes.HANDLE(-1).value
    _NOT_FOUND = (2, 3)                         # ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND


def open_shared(path):
    """Open `path` read-only in binary mode, sharing read, write and delete with other processes.

    Returns an ordinary unbuffered file object; close it as soon as the read is done. Raises
    FileNotFoundError when the file is missing, OSError otherwise. Off Windows this is plain open().
    """
    if not IS_WINDOWS:
        return open(path, "rb", buffering=0)
    handle = _CreateFileW(str(path), _GENERIC_READ, _FILE_SHARE_ALL, None, _OPEN_EXISTING,
                          _FILE_ATTRIBUTE_NORMAL, None)
    if handle == _INVALID_HANDLE or handle is None:
        err = ctypes.get_last_error()
        if err in _NOT_FOUND:
            raise FileNotFoundError(2, "No such file", str(path))
        raise ctypes.WinError(err)
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except Exception:
        _CloseHandle(handle)
        raise
    # From here the descriptor owns the handle: closing the file object closes both.
    return os.fdopen(fd, "rb", buffering=0)
