"""Only one HeadMouse at a time (Windows).

A second copy would fight the first over the webcam and the keys. When HeadMouse
is already running, starting it again brings the existing window to the front
instead of opening another one.
"""

import ctypes
import sys

MUTEX_NAME = "Local\\HeadMouse.SingleInstance"
ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9

_handle = None  # kept for the life of the process; Windows releases it on exit


def acquire():
    """True if this is the only HeadMouse running (always True off Windows)."""
    global _handle
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
    _handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def show_existing_window():
    """Bring the running HeadMouse window to the front."""
    if sys.platform != "win32":
        return False
    user32 = ctypes.WinDLL("user32")
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.FindWindowW.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
    user32.ShowWindow.argtypes = (ctypes.c_void_p, ctypes.c_int)
    user32.SetForegroundWindow.argtypes = (ctypes.c_void_p,)
    hwnd = user32.FindWindowW(None, "HeadMouse")
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    return True
