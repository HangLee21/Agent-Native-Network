import ctypes,os,sys
k=ctypes.WinDLL("kernel32",use_last_error=True);k.FreeConsole()
if not k.AttachConsole(50896):raise OSError(ctypes.get_last_error(),"AttachConsole failed")
k.SetConsoleCtrlHandler(None,True)
a=(ctypes.c_ulong*32)();n=k.GetConsoleProcessList(a,32);ids=set(a[:n]);allowed={50896,13796,13272,os.getpid()}
print("console_processes",sorted(ids),flush=True)
if not {50896,13796,13272}.issubset(ids) or ids-allowed:raise RuntimeError("unexpected console owners; no stop sent")
if not k.GenerateConsoleCtrlEvent(0,0):raise OSError(ctypes.get_last_error(),"CTRL_C failed")
print("sent graceful stop",flush=True);k.FreeConsole()
