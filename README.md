# HeadMouse: joystick-style head control for OpenTrack

HeadMouse turns the head angle reported by **OpenTrack 2026.1.0** into **continuous mouse
movement**, like a joystick, so you can steer a game camera (here: Enshrouded) with small head
movements and keep your left hand on the keyboard.

| Head | Camera |
|---|---|
| Centered (inside the dead zone) | Stops |
| Turned a little right | Turns right slowly, and *keeps* turning while you hold it |
| Turned further right | Turns right faster |
| Moving back toward center | Slows down. **Never reverses.** |
| Turned left / up / down | Same, in that direction, each with its own settings |
| **F9 held** (or foot pedal) | Freezes instantly. Re-center your head, then release |

It runs alongside OpenTrack. Nothing in OpenTrack's installation or in the game is changed.

```
Webcam -> OpenTrack (tracking, filtering, Center key) -> UDP 127.0.0.1:4242
       -> HeadMouse (dead zones, 4 speed curves, pause, safety) -> Windows SendInput -> Enshrouded
```

> **Status:** Phase 1 prototype. The logic is covered by automated tests and was run end to end
> with simulated OpenTrack data. Windows-only parts (mouse output, key reading) haven't been run
> on Windows yet. Steps 4–7 below are the first real test.

---

## 1. What you need

1. **Windows 11** with **OpenTrack 2026.1.0** already tracking your head.
2. **Python 3.11 or newer** (3.13 recommended) from <https://www.python.org/downloads/windows/>.
   In the installer, tick **"Add python.exe to PATH"**. The installer also adds the `py`
   command used by the `.bat` files. No other packages are needed.
3. This folder, copied anywhere (e.g. `C:\HeadMouse`). From GitHub: **Code → Download ZIP**,
   then extract it.

Check the install: open the folder and double-click **`Run tests.bat`**. The last line should be
`OK`.

## 2. Set up OpenTrack (one time)

Your existing OpenTrack profile is left untouched; this adds a second one.

1. In OpenTrack, use the **profile** drop-down menu to create a **new copied config** (it keeps
   your camera and tracker settings). Name it e.g. `HeadMouse`.
2. **Output:** choose **"UDP over network"**, then click the settings (hammer) button next to it:
   - IP address: **127.0.0.1** (the default is 192.168.0.2, which won't work)
   - Port: **4242**

   This replaces "mouse emulation". OpenTrack has one output at a time, so its own mouse
   movement stops in this profile.
3. **Mapping:** HeadMouse's angles should be your real head angles. Open **Mapping** and make the
   **Yaw** and **Pitch** curves a plain straight diagonal line. A curve with no points is exactly
   1:1 in OpenTrack 2026.1.0. Delete any points you added for mouse emulation.
4. **Filter:** keep the filter you use (e.g. Accela or NaturalMovement). Its smoothing is
   passed straight through to HeadMouse.
5. **Options → Shortcuts:** set a **Center** key if you haven't already. It recenters OpenTrack,
   and HeadMouse follows automatically. Don't give it the same key as HeadMouse's keys.
6. Press **Start** in OpenTrack.

## 3. Step-by-step testing

Do the steps in order. Each one checks one piece.

**Step 1: Is OpenTrack data arriving? (no mouse movement)**
Double-click **`Monitor OpenTrack.bat`**. You should see roughly 60–250 *packets/s* and the
words follow your head: turn right → `RIGHT`, look up → `UP`.
- Shows `LEFT` when you turn right → set `yaw_right_is_positive = false` in the settings.
- Shows `DOWN` when you look up → set `pitch_up_is_positive = false`.
- A comfortable small head turn should read about 10–20. If it reads 60 or more, the OpenTrack
  mapping curve is still amplifying (see section 2, step 3).

**Step 2: Check the speed tables (no mouse movement)**
Double-click **`Show speed curves.bat`** to see the camera speed for every head angle in all four
directions.

**Step 3: Dry run (no mouse movement)**
Double-click **`Dry Run.bat`**. Press **F10** to enable. The status line shows the state and the
speed it *would* use, e.g. `ACTIVE  yaw +10.0 pitch +0.0 | right  54  -     0 deg/s`. Check:
- Hold your head right → speed stays steady. Turn further → it rises.
- Move back toward center → it falls to 0 and never shows `left`.
- Hold **F9** → `PAUSED` and 0. Center your head, release → still 0.
- Cover the camera → after about 1 s: `STOPPED: tracking frozen` (or `no tracking data`).

**Step 4: Desktop test (real mouse movement)**
Double-click **`Start HeadMouse.bat`** and press **F10**. The desktop cursor should glide while
your head is turned and stop when centered. Repeat the Step 3 checks. Press **F10** to turn it
off. Desktop speeds won't match the game; that's expected.

*No camera handy?* In a second window run `py tools\fake_opentrack.py --yaw 10` (holds a fake
10° right turn; Ctrl+C stops it, and the cursor must stop within about 0.25 s). Also try
`--sweep`, or `--yaw 15 --freeze-after 3` to simulate OpenTrack losing your face.

**Step 5: Calibrate for Enshrouded**
Enshrouded's mouse sensitivity decides how many mouse counts make one full turn.
1. Start Enshrouded and pick your mouse sensitivity (changing it later means recalibrating).
2. Double-click **`Calibrate.bat`** (head tracking is off in this mode).
3. In the game, face a landmark and press **F6**. The camera turns for 3 seconds.
4. Overshot or undershot? Edit `counts_per_360` in `headmouse_settings.toml`, save, and press
   F6 again (the new value is read on every press).
   *New value = old value × 360 ÷ degrees it actually turned.*
   For example, it turned about 1.5 turns (540°) with 4000: 4000 × 360 ÷ 540 = 2667.

After this, the speeds in the settings file are real in-game degrees per second.

**Step 6: Try it in Enshrouded**
Start OpenTrack, `Start HeadMouse.bat`, then Enshrouded. Press **F10** in game. Try a full 360°
turn, holding F9 to stop, looking up and down, and precision mode (hold F7).
If it works, consider setting `only_when_window_title_contains = "Enshrouded"` so the cursor
never moves when you alt-tab out.

**Step 7: Tune the curves.** See section 5.

## 4. Keys

All keys can be changed in `[keys]`. Keys are only *watched*, never blocked, so the game also
receives them. Pick keys Enshrouded doesn't use. A USB foot pedal programmed to send F9 works
exactly like F9.

| Key | Action |
|---|---|
| **F10** | Head control on/off (starts **off**; change with `start_enabled`) |
| **F9** (hold) | Freeze camera immediately; release to resume. Overrides everything |
| **F7** (hold) | Precision mode: 80% slower (`precision_speed_factor = 0.2`) |
| **F8** | Look straight ahead and press: sets the neutral position |
| OpenTrack's Center key | Recenters OpenTrack itself (preferred way to recenter) |

About F8 versus OpenTrack's Center: F8 is a correction inside HeadMouse only. If you press
OpenTrack's Center key after using F8, press F8 once more while looking straight ahead. It is
easiest to use just one of them, preferably OpenTrack's.

## 5. Tuning the four directions

Open `headmouse_settings.toml` in Notepad. **Changes apply as soon as you save**, even while
playing. Each of `[right]`, `[left]`, `[up]` and `[down]` has:

| Setting | Meaning |
|---|---|
| `deadzone` | Head angle with no movement (default 3° horizontal, 2° vertical) |
| `min_speed` | Camera speed just outside the dead zone |
| `max_speed` | Top camera speed (180°/s horizontal, 60°/s vertical) |
| `full_speed_angle` | Head angle where top speed is reached (15° / 10°) |
| `curve` | 1 = linear; higher = more precision near center, faster ramp further out |

The defaults follow your requested tables to within about 10%. Run `Show speed curves.bat` to
see the exact values. To reproduce a table exactly instead, add for example
`points = [[3, 0], [5, 10], [8, 25], [10, 60], [12, 100], [15, 180]]` to that direction.

**Examples:**
- *Looking down feels sluggish:* in `[down]` only, lower `deadzone` to 1.5 and
  `full_speed_angle` to 8, or raise `max_speed`.
- *Turning too fast overall:* lower `max_speed` in `[left]` and `[right]`.
- *Hard to make small adjustments:* raise `curve` (e.g. 3.0) or `deadzone`.
- *Jittery near the dead-zone edge:* raise `[motion] deadzone_hysteresis` or `smoothing_seconds`.

## 6. Safety behavior

HeadMouse stops all movement, rather than guessing, when:
- OpenTrack sends nothing for 0.25 s (`no_data_timeout`)
- OpenTrack keeps sending *exactly* the same numbers for 1 s (`frozen_data_timeout`). This is
  what usually happens when it loses your face.
- The angle jumps more than 25° between updates (`max_jump_degrees`): movement is held for 0.5 s
- The data is impossible (not a number, or beyond 120° yaw / 90° pitch)
- F9 is held, head control is off, or the game window isn't active (if that option is set)

Leftover fractions of a mouse count are thrown away on every stop, so nothing jumps on resume.
Direction only reverses after the head has rested in the dead zone for 0.15 s
(`reverse_delay_seconds`), so a quick overshoot past center can't flip the camera.
`require_center_to_resume = true` makes movement wait for a centered head after any pause.

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| `Waiting for data from OpenTrack` | Is OpenTrack started? Is the output "UDP over network" with 127.0.0.1 and port 4242? |
| Windows Firewall asks about Python | HeadMouse only listens on this PC (127.0.0.1). Allowing *Private networks* is enough. |
| `cannot listen on 127.0.0.1:4242` | HeadMouse is already open in another window, or another app uses the port. Close it or change the port in both places. |
| `'py' is not recognized` | Reinstall Python with "Add python.exe to PATH", or replace `py` with `python` in the .bat files. |
| Desktop cursor moves but not in the game | Click into the game window first. If Enshrouded runs as administrator, run HeadMouse as administrator too (HeadMouse prints a warning when Windows refuses the movement). |
| Movement stops while holding your head perfectly still | OpenTrack's filter can output identical numbers when you're very still. Raise `frozen_data_timeout` (e.g. 2.0) or set it to 0. |
| Speeds feel wrong in the game | Recalibrate `counts_per_360` (Step 5). Turning off Windows "Enhance pointer precision" can make the desktop test more predictable. |
| Turns the wrong way | Steps 1 and 3: the `*_is_positive` settings; `invert_vertical` for up/down only. |
| Pressing F9/F10 does something in the game | Choose other keys in `[keys]` (e.g. `"PAUSE"`, `"SCROLLLOCK"`). |
| Drifts slowly with head centered | Press OpenTrack's Center key (or F8) while looking straight ahead, or raise that direction's `deadzone`. |

## 8. For the developer

```
headmouse/tracking.py    where angles come from (OpenTrack UDP: 6 little-endian doubles X,Y,Z,yaw,pitch,roll)
headmouse/safety.py      decides whether tracking data can be trusted
headmouse/curves.py      head angle -> camera speed for one direction
headmouse/controller.py  joystick logic: dead zones, no-reverse rule, pause, fractions -> mouse counts
headmouse/winput.py      Windows SendInput / GetAsyncKeyState (the only Windows-specific code)
headmouse/config.py      settings file loading and validation
headmouse/app.py         main loop and the --monitor / --dry-run / --curves / --calibrate modes
tools/fake_opentrack.py  simulated OpenTrack sender
tests/                   py -m unittest -v
```

The tracking input is separate from the mouse logic. A different tracker (e.g. eViacam output or
another UDP format) only needs a new class in `tracking.py` with `start()`, `stop()` and
`latest()` returning a `HeadSample`.

Mouse movement uses `SendInput` with `MOUSEEVENTF_MOVE`, the same call OpenTrack's own mouse
output uses in its default mode. Nothing is injected into the game process and no game files are
touched.

**Phase 3, packaging:** `build_exe.bat` builds `dist\HeadMouse.exe` with PyInstaller (keep
`headmouse_settings.toml` beside it). This is untested so far.
