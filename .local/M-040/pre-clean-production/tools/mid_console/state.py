"""Local durable console state. No device operations and no HTTP-selected paths."""
import ctypes
import json
import os
from pathlib import Path


def process_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return True  # Unknown owner is never treated as dead.
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() not in (87, 1168)
        try:
            code = ctypes.c_ulong()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class StateStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'state.json'

    def load(self):
        return json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else None

    def save(self, plans, runs, active):
        value = dict(schema='mid.console.state.v1', plans=plans, active=active,
                     runs={rid: {k: v for k, v in record.items() if k != 'stop_event'} for rid, record in runs.items()})
        temp = self.directory / 'state.tmp.json'
        temp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        temp.replace(self.path)
