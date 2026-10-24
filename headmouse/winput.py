"""Windows input: sending relative mouse movement and reading key states.

WindowsInput uses SendInput with MOUSEEVENTF_MOVE, the same call OpenTrack's own
mouse output uses in its default "direct" mode. Keys are only *read* with
GetAsyncKeyState, so normal keyboard input is never blocked or changed.
"""

import contextlib
import ctypes
import os
import sys

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_MOVE_NOCOALESCE = 0x2000
BUTTON_FLAGS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}  # (down, up)

# Fixed-width field types so the structure layout matches Windows on 64-bit and
# 32-bit Python (ctypes.wintypes.LONG would be 8 bytes on Linux, which breaks the
# size self-check in the tests).
_ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_int32), ("dy", ctypes.c_int32),
                ("mouseData", ctypes.c_uint32), ("dwFlags", ctypes.c_uint32),
                ("time", ctypes.c_uint32), ("dwExtraInfo", _ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_uint16), ("wScan", ctypes.c_uint16),
                ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32),
                ("dwExtraInfo", _ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_uint32), ("wParamL", ctypes.c_uint16),
                ("wParamH", ctypes.c_uint16)]


class _INPUTUNION(ctypes.Union):
    # All three members must be present so the union has Windows' size.
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("u", _INPUTUNION)]


class CURSORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("flags", ctypes.c_uint32), ("hCursor", ctypes.c_void_p),
                ("x", ctypes.c_int32), ("y", ctypes.c_int32)]


CURSOR_SHOWING = 0x00000001


class WindowsInput:
    def __init__(self):
        from ctypes import wintypes
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        self._user32.SendInput.restype = wintypes.UINT
        self._user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
        self._user32.GetAsyncKeyState.restype = ctypes.c_short
        self._user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        self._user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        self._user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        self._user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self._user32.GetCursorInfo.argtypes = (ctypes.POINTER(CURSORINFO),)
        self._user32.GetCursorInfo.restype = wintypes.BOOL
        self._pid = os.getpid()
        self._input = INPUT(type=INPUT_MOUSE)
        self.failed_sends = 0

    def send_relative(self, dx, dy):
        mi = self._input.u.mi
        mi.dx, mi.dy = int(dx), int(dy)
        mi.mouseData = 0
        mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_MOVE_NOCOALESCE
        mi.time = 0
        mi.dwExtraInfo = 0
        if self._user32.SendInput(1, ctypes.byref(self._input), ctypes.sizeof(INPUT)) != 1:
            # Note: when Windows blocks input to an administrator window it does NOT
            # report failure, so this only catches other errors.
            self.failed_sends += 1

    def send_button(self, button, down):
        """Press or release a mouse button ("left", "right", "middle")."""
        mi = self._input.u.mi
        mi.dx = mi.dy = 0
        mi.mouseData = 0
        mi.dwFlags = BUTTON_FLAGS[button][0 if down else 1]
        mi.time = 0
        mi.dwExtraInfo = 0
        if self._user32.SendInput(1, ctypes.byref(self._input), ctypes.sizeof(INPUT)) != 1:
            self.failed_sends += 1

    def is_key_down(self, vk):
        return vk is not None and bool(self._user32.GetAsyncKeyState(vk) & 0x8000)

    def pointer_visible(self):
        """True while Windows shows a mouse pointer (games hide it while the mouse turns the camera).
        A game can also hide it with SetCursor(NULL), which leaves the SHOWING flag set - hence hCursor."""
        info = CURSORINFO(cbSize=ctypes.sizeof(CURSORINFO))   # its own buffer: called from two threads
        if not self._user32.GetCursorInfo(ctypes.byref(info)):
            return False
        return bool(info.flags & CURSOR_SHOWING) and bool(info.hCursor)

    def foreground_window_title(self):
        hwnd = self._user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = ctypes.c_ulong()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == self._pid:
            # Our own window: asking for its title waits on the Tk thread, which
            # can deadlock while that thread is shutting the engine down.
            return ""
        length = self._user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        self._user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value


class NullInput:
    """Stand-in used for --dry-run, on non-Windows systems and in tests.

    Records movement instead of sending it; key states can be set by tests.
    """

    def __init__(self):
        self.sent = []
        self.keys_down = set()
        self.window_title = ""
        self.pointer = False
        self.buttons = []           # (button, down) in the order they were sent
        self.failed_sends = 0

    def send_relative(self, dx, dy):
        self.sent.append((int(dx), int(dy)))

    def send_button(self, button, down):
        self.buttons.append((button, down))

    def is_key_down(self, vk):
        return vk is not None and vk in self.keys_down

    def pointer_visible(self):
        return self.pointer

    def foreground_window_title(self):
        return self.window_title


class KeyReader(NullInput):
    """Reads keys from Windows but never sends mouse movement (for --dry-run)."""

    def __init__(self):
        super().__init__()
        self._win = WindowsInput() if sys.platform == "win32" else None

    def is_key_down(self, vk):
        return self._win.is_key_down(vk) if self._win else super().is_key_down(vk)

    def pointer_visible(self):
        return self._win.pointer_visible() if self._win else super().pointer_visible()

    def foreground_window_title(self):
        return self._win.foreground_window_title() if self._win else super().foreground_window_title()


@contextlib.contextmanager
def high_resolution_timer():
    """Ask Windows for 1 ms timer resolution so the output loop ticks evenly."""
    if sys.platform != "win32":
        yield
        return
    winmm = ctypes.WinDLL("winmm")
    winmm.timeBeginPeriod(1)
    try:
        yield
    finally:
        winmm.timeEndPeriod(1)
