"""Key names used in the settings file, mapped to Windows virtual-key codes.

Kept free of Windows imports so settings can be validated on any platform.
"""

_NAMED_KEYS = {
    "SPACE": 0x20, "TAB": 0x09, "ENTER": 0x0D, "BACKSPACE": 0x08,
    "CAPSLOCK": 0x14, "SCROLLLOCK": 0x91, "NUMLOCK": 0x90, "PAUSE": 0x13,
    "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "SHIFT": 0x10, "CTRL": 0x11, "ALT": 0x12,
    "LSHIFT": 0xA0, "RSHIFT": 0xA1, "LCTRL": 0xA2, "RCTRL": 0xA3,
    "LALT": 0xA4, "RALT": 0xA5,
    "BACKTICK": 0xC0, "MINUS": 0xBD, "EQUALS": 0xBB,
    "LEFTBRACKET": 0xDB, "RIGHTBRACKET": 0xDD, "SEMICOLON": 0xBA,
    "QUOTE": 0xDE, "COMMA": 0xBC, "PERIOD": 0xBE, "SLASH": 0xBF,
    "BACKSLASH": 0xDC,
    "LEFTMOUSE": 0x01, "RIGHTMOUSE": 0x02, "MIDDLEMOUSE": 0x04, "MOUSE4": 0x05, "MOUSE5": 0x06,
    "NUMPADMULTIPLY": 0x6A, "NUMPADADD": 0x6B, "NUMPADSUBTRACT": 0x6D,
    "NUMPADDECIMAL": 0x6E, "NUMPADDIVIDE": 0x6F,
}

for _i in range(1, 25):
    _NAMED_KEYS[f"F{_i}"] = 0x70 + _i - 1
for _i in range(10):
    _NAMED_KEYS[f"NUMPAD{_i}"] = 0x60 + _i
    _NAMED_KEYS[str(_i)] = ord(str(_i))
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    _NAMED_KEYS[_c] = ord(_c)

DISABLED_NAMES = ("", "NONE", "OFF")


def key_code(name):
    """Return the virtual-key code for a key name, or None if the key is disabled.

    Accepts names like "F9", "CAPSLOCK", "A", "NUMPAD5" or a hex code such as "0x78".
    Raises ValueError for unknown names.
    """
    text = str(name).strip().upper().replace(" ", "").replace("_", "")
    if text in DISABLED_NAMES:
        return None
    if text.startswith("0X"):
        code = int(text, 16)
        if not 0 < code < 0xFF:
            raise ValueError(f"key code {name!r} is out of range")
        return code
    if text not in _NAMED_KEYS:
        raise ValueError(f"unknown key name {name!r}")
    return _NAMED_KEYS[text]


_TK_KEYSYMS = {
    "Pause": "PAUSE", "Scroll_Lock": "SCROLLLOCK", "Caps_Lock": "CAPSLOCK", "Num_Lock": "NUMLOCK",
    "Insert": "INSERT", "Delete": "DELETE", "Home": "HOME", "End": "END",
    "Prior": "PAGEUP", "Next": "PAGEDOWN", "Left": "LEFT", "Right": "RIGHT", "Up": "UP", "Down": "DOWN",
    "space": "SPACE", "Tab": "TAB", "Return": "ENTER", "BackSpace": "BACKSPACE",
    "Shift_L": "LSHIFT", "Shift_R": "RSHIFT", "Control_L": "LCTRL", "Control_R": "RCTRL",
    "Alt_L": "LALT", "Alt_R": "RALT", "grave": "BACKTICK", "minus": "MINUS", "equal": "EQUALS",
    "bracketleft": "LEFTBRACKET", "bracketright": "RIGHTBRACKET", "semicolon": "SEMICOLON",
    "apostrophe": "QUOTE", "comma": "COMMA", "period": "PERIOD", "slash": "SLASH", "backslash": "BACKSLASH",
    "KP_Multiply": "NUMPADMULTIPLY", "KP_Add": "NUMPADADD", "KP_Subtract": "NUMPADSUBTRACT",
    "KP_Decimal": "NUMPADDECIMAL", "KP_Divide": "NUMPADDIVIDE",
}
for _i in range(10):
    _TK_KEYSYMS[f"KP_{_i}"] = f"NUMPAD{_i}"


def name_from_tk_keysym(keysym):
    """Settings-file key name for a Tk key event's keysym, or None if unsupported."""
    if keysym in _TK_KEYSYMS:
        return _TK_KEYSYMS[keysym]
    upper = keysym.upper()
    if (len(upper) == 1 and upper.isalnum()) or (upper.startswith("F") and upper[1:].isdigit()
                                                 and 1 <= int(upper[1:]) <= 24):
        return upper
    return None
