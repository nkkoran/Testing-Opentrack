"""Start the HeadMouse window without a console (used by the desktop shortcut)."""

import sys
import traceback
from pathlib import Path

try:
    from headmouse.app import main
    sys.exit(main())
except SystemExit:
    raise
except BaseException:
    log = Path(__file__).resolve().parent / "headmouse_error.log"
    log.write_text(traceback.format_exc(), encoding="utf-8")
    try:
        from tkinter import messagebox
        messagebox.showerror("HeadMouse", f"HeadMouse stopped because of an error.\n\nDetails: {log}")
    except Exception:
        pass
    sys.exit(1)
