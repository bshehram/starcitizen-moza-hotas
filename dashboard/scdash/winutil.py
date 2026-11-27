"""Every Windows-only call, each with a harmless fallback elsewhere.

- `open_shared()`: open the game's log so that the game can still write, truncate, rename or
  delete it while we read. Python's own open() shares read and write on Windows but not delete
  (PLAN §8). The game empties Game.log in place at each launch in this build, so nothing deletes
  it today, but a patch could change that, and a reader must never be the reason it fails.
- `InstanceLock`: the single-instance lock, a named mutex (PLAN §6). Off Windows, an advisory
  lock on a file.
- `process_list()` / `process_running()`: the names of running programs from a Toolhelp
  snapshot. That reads the system's process list without opening any process, so the game's
  process is never touched (PLAN §6, §8). Never `tasklist`, PowerShell or WMI: starting a program
  every 10 seconds would cost more than the service's whole budget.
- `below_normal_priority()`: the service yields to the game (PLAN §8).
- `exclusive_address()`: no second program may bind the service's port (PLAN §6).
- `own_memory()`: this process's memory, for `status` (PLAN §9).

- `process_created()`: a process's creation time, to tell a live instance of ours from a reused
  process id.

Nothing here opens the game's process, or any process to change it. The calls that take a process
handle use `GetCurrentProcess()`, a pseudo-handle for this process; the one exception,
`process_created(pid)`, opens a query-only handle and only to a process the snapshot names
python.exe or pythonw.exe. Nothing here, or anywhere in scdash, ends or signals a process.
"""
import os
import socket
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

    # Named mutex.
    _CreateMutexW = _kernel32.CreateMutexW
    _CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _CreateMutexW.restype = wintypes.HANDLE
    _OpenMutexW = _kernel32.OpenMutexW
    _OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    _OpenMutexW.restype = wintypes.HANDLE
    _ERROR_ALREADY_EXISTS = 183
    _SYNCHRONIZE = 0x00100000

    # Toolhelp process snapshot.
    _TH32CS_SNAPPROCESS = 0x2

    class _PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    _CreateToolhelp32Snapshot = _kernel32.CreateToolhelp32Snapshot
    _CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _Process32FirstW = _kernel32.Process32FirstW
    _Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    _Process32FirstW.restype = wintypes.BOOL
    _Process32NextW = _kernel32.Process32NextW
    _Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    _Process32NextW.restype = wintypes.BOOL

    # This process.
    _GetCurrentProcess = _kernel32.GetCurrentProcess
    _GetCurrentProcess.argtypes = []
    _GetCurrentProcess.restype = wintypes.HANDLE
    _SetPriorityClass = _kernel32.SetPriorityClass
    _SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _SetPriorityClass.restype = wintypes.BOOL
    _GetPriorityClass = _kernel32.GetPriorityClass
    _GetPriorityClass.argtypes = [wintypes.HANDLE]
    _GetPriorityClass.restype = wintypes.DWORD
    _BELOW_NORMAL_PRIORITY_CLASS = 0x00004000

    # Creation time of a process: this one through its pseudo-handle, one of our own Python
    # processes through a query-only handle. Never the game's: see process_created().
    class _FILETIME(ctypes.Structure):
        _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]

    _GetProcessTimes = _kernel32.GetProcessTimes
    _GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(_FILETIME)] * 4
    _GetProcessTimes.restype = wintypes.BOOL
    _OpenProcess = _kernel32.OpenProcess
    _OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _OpenProcess.restype = wintypes.HANDLE
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000     # the only access ever asked for

    class _PROCESS_MEMORY_COUNTERS_EX2(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t),
                    # Windows 10 1809 and later fill these two when cb covers them.
                    ("PrivateWorkingSetSize", ctypes.c_size_t), ("SharedCommitUsage", ctypes.c_ulonglong)]

    try:
        _psapi = ctypes.WinDLL("psapi", use_last_error=True)
        _GetProcessMemoryInfo = _psapi.GetProcessMemoryInfo
        _GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        _GetProcessMemoryInfo.restype = wintypes.BOOL
    except OSError:                              # pragma: no cover - psapi is always there
        _GetProcessMemoryInfo = None


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


# ------------------------------------------------------------------------- single instance

class InstanceLock:
    """The single-instance lock (PLAN §6). `acquire()` returns True when this process now holds
    it, False when another process does. The operating system drops it when the holder exits,
    however it exits, so a crash never leaves a lock behind.

    On Windows it is a named mutex in the session's own namespace (`Local\\`): the mutex exists
    for as long as one handle to it is open, so holding the handle is holding the lock. `name`
    must be a plain word; it is derived from the data folder, so a test instance and a replay
    (each with a folder of its own) can run beside the live one. Elsewhere it is an advisory
    lock on `lock_path`.
    """

    def __init__(self, name, lock_path):
        self.name = name
        self.lock_path = lock_path
        self._handle = None
        self._file = None

    def acquire(self):
        if self._handle is not None or self._file is not None:
            return True
        if IS_WINDOWS:
            h = _CreateMutexW(None, False, "Local\\" + self.name)
            err = ctypes.get_last_error()
            if not h:
                raise ctypes.WinError(err)
            if err == _ERROR_ALREADY_EXISTS:
                _CloseHandle(h)
                return False
            self._handle = h
            return True
        try:
            import fcntl
        except ImportError:                       # pragma: no cover - no locking at all
            return True
        f = open(self.lock_path, "a+b")
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return False
        self._file = f
        return True

    def held_elsewhere(self):
        """Is the lock held by some process (not this object)? Read-only: it does not take it."""
        if self._handle is not None or self._file is not None:
            return False
        if IS_WINDOWS:
            h = _OpenMutexW(_SYNCHRONIZE, False, "Local\\" + self.name)
            if h:
                _CloseHandle(h)
                return True
            return False
        try:
            import fcntl
        except ImportError:                       # pragma: no cover
            return False
        if not os.path.exists(self.lock_path):
            return False
        with open(self.lock_path, "a+b") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return False

    def release(self):
        if self._handle is not None:
            _CloseHandle(self._handle)
            self._handle = None
        if self._file is not None:
            try:
                self._file.close()
            finally:
                self._file = None


# ------------------------------------------------------------------------- processes

def process_list():
    """[(pid, exe name)] of every running process, from a Toolhelp snapshot: no process is opened.
    Off Windows, from /proc where there is one, else an empty list (the game runs on Windows)."""
    if IS_WINDOWS:
        snap = _CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if snap == _INVALID_HANDLE or not snap:
            raise ctypes.WinError(ctypes.get_last_error())
        out = []
        try:
            entry = _PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
            ok = _Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                out.append((entry.th32ProcessID, entry.szExeFile))
                ok = _Process32NextW(snap, ctypes.byref(entry))
        finally:
            _CloseHandle(snap)
        return out
    out = []
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return out
    for p in pids:
        try:
            with open("/proc/%s/comm" % p, "rb") as f:
                out.append((int(p), f.read().decode("utf-8", "replace").strip()))
        except OSError:
            continue
    return out


def process_running(name, plist=None):
    """Is a process with this exe name running? Case-insensitive, by name only."""
    want = name.lower()
    for _pid, exe in (plist if plist is not None else process_list()):
        if exe.lower() == want:
            return True
    return False


def process_name(pid, plist=None):
    """The exe name of the process with this id, or None when there is none."""
    for p, exe in (plist if plist is not None else process_list()):
        if p == pid:
            return exe
    return None


PYTHON_NAMES = ("python.exe", "pythonw.exe", "python", "python3", "pythonw")


def process_created(pid=None, plist=None):
    """When a process was created, in seconds since the epoch (to 100 ns), or None.

    pid None: this process, through its pseudo-handle (nothing is opened). Another pid: only when
    the process list names it python.exe or pythonw.exe, through a handle that can only query
    (PROCESS_QUERY_LIMITED_INFORMATION). The game's process is never opened: its name is not on
    that list. Used to tell a live instance of ours from a reused process id. Off Windows: None."""
    if not IS_WINDOWS:
        return None
    if pid is None or pid == os.getpid():
        handle, opened = _GetCurrentProcess(), False
    else:
        name = process_name(pid, plist)
        if name is None or name.lower() not in PYTHON_NAMES:
            return None
        handle = _OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        opened = True
    try:
        times = [_FILETIME() for _ in range(4)]
        if not _GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
            return None
        ft = (times[0].hi << 32) | times[0].lo          # 100 ns units since 1601-01-01
        return ft / 1e7 - 11644473600.0
    finally:
        if opened:
            _CloseHandle(handle)


# ------------------------------------------------------------------------- this process

def below_normal_priority():
    """Run this process below normal priority. Returns True when it took. Children started
    afterwards inherit it [seen 2026-11-27, PLAN §6]."""
    if IS_WINDOWS:
        return bool(_SetPriorityClass(_GetCurrentProcess(), _BELOW_NORMAL_PRIORITY_CLASS))
    try:
        os.nice(5)
        return True
    except (AttributeError, OSError):
        return False


def is_below_normal():
    if IS_WINDOWS:
        return _GetPriorityClass(_GetCurrentProcess()) == _BELOW_NORMAL_PRIORITY_CLASS
    try:
        return os.nice(0) > 0
    except (AttributeError, OSError):
        return False


def exclusive_address(sock):
    """Before bind(): no other socket may bind this address and port while this one holds it.
    Windows lets a second socket bind a port held under SO_REUSEADDR [seen 2026-11-26];
    SO_EXCLUSIVEADDRUSE refuses that. Elsewhere a listening port is exclusive already."""
    opt = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
    if IS_WINDOWS and opt is not None:
        sock.setsockopt(socket.SOL_SOCKET, opt, 1)


def own_memory():
    """This process's memory in bytes: `private_ws` (the private working set, the figure Task
    Manager shows as memory), `working_set`, `peak_working_set` and `private` (committed). A
    field the platform cannot give is None."""
    out = {"private_ws": None, "working_set": None, "peak_working_set": None, "private": None}
    if IS_WINDOWS and _GetProcessMemoryInfo is not None:
        c = _PROCESS_MEMORY_COUNTERS_EX2()
        c.cb = ctypes.sizeof(c)
        if not _GetProcessMemoryInfo(_GetCurrentProcess(), ctypes.byref(c), c.cb):
            # An older Windows: the structure without the last two fields.
            c.cb = ctypes.sizeof(c) - ctypes.sizeof(ctypes.c_size_t) - ctypes.sizeof(ctypes.c_ulonglong)
            if not _GetProcessMemoryInfo(_GetCurrentProcess(), ctypes.byref(c), c.cb):
                return out
            out["private_ws"] = None
        else:
            out["private_ws"] = c.PrivateWorkingSetSize or None
        out["working_set"] = c.WorkingSetSize
        out["peak_working_set"] = c.PeakWorkingSetSize
        out["private"] = c.PrivateUsage
        return out
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        out["peak_working_set"] = peak if sys.platform == "darwin" else peak * 1024
    except (ImportError, OSError, ValueError):
        pass
    return out
