# HeadMouse: head control for games, joystick-style

HeadMouse lets you steer a game camera (here: Enshrouded) with small head movements and keep your
left hand on the keyboard. How far your head is turned sets **how fast the camera turns**, like a
joystick:

| Head | Camera |
|---|---|
| Centered (inside the dead zone) | Stops |
| Turned a little right | Turns right slowly, and *keeps* turning while you hold it |
| Turned further right | Turns right faster |
| Moving back toward center | Slows down. **Never reverses.** |
| Turned left / up / down | Same, each direction with its own settings |
| **F9 held** (or foot pedal) | Freezes instantly. Re-center your head, then release |

It reads your **webcam directly** (built-in face tracking, no other program needed) or can use
**OpenTrack** instead. Nothing in the game or in OpenTrack's installation is modified.

> **Status:** every change is built and tested on Windows by GitHub Actions. That covers the unit
> tests (including real Windows calls and real MediaPipe face tracking), the packaged app's
> self-check, and installing, updating and uninstalling. Live webcam use and mouse movement inside
> Enshrouded can only be tested on the real PC (section 3).

---

## 1. Install

**Download and double-click:** get **HeadMouse-Setup.exe** from the
[latest release](https://github.com/nkkoran/Testing-Opentrack/releases/latest)
([direct link](https://github.com/nkkoran/Testing-Opentrack/releases/latest/download/HeadMouse-Setup.exe))
and double-click it.

- Everything is included: no Python and no other downloads. It installs for your user only, so
  no administrator password is needed.
- It adds HeadMouse to the Start menu and the desktop, and you can uninstall it from Settings → Apps.
- HeadMouse starts when the installer finishes.
- Windows may say *"Windows protected your PC"*, because the app isn't code-signed. Click
  **More info → Run anyway**.

**Or with one command,** which also skips that Windows warning: press **Win + R**, paste this, and
press **Enter**:

```
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/nkkoran/Testing-Opentrack/master/install.ps1 | iex"
```

**Updates:** HeadMouse tells you when a new version is out. Press **Update** in the top bar and it
updates and restarts; your settings are kept. Running the installer or the command again also
updates.

*From source (for the developer):* download the ZIP, extract it, and double-click `Setup.bat`. It
installs Python if needed, then HeadMouse's parts, and creates the icons.

## 2. First start: the setup wizard

HeadMouse opens by itself after installing, and the first time the **setup wizard** opens too:

1. **Choose the tracker.** "Built-in webcam" is recommended. A camera preview shows a green dot on
   your nose when your face is found.
2. **Look at the middle of the screen** and hold still for 3 seconds.
3. **Turn right, left, up and down**, each as far as is *comfortable* (no straining), and hold until
   the beep.
4. HeadMouse sets each direction's **dead zone** and **full-speed angle** to suit your movement,
   and fixes reversed directions automatically. Press **Save and finish**.

Full speed is reached at 75% of your comfortable range, so you never need to strain. A direction
you can move less (e.g. down) gets its own, more sensitive settings. Run the wizard again any time
from the main window.

## 3. Test it, then calibrate for the game

**Desktop test:** flip the **Head control** switch (or press F10). The cursor glides while your head is turned and stops
when centered. Hold **F9**: it freezes. Cover the camera: within a second the window turns red
(**NO TRACKING**) and you hear a low double tone.

**Game calibration (optional, recommended):** this makes the speeds real in-game degrees per
second. Skip it if turning already feels right.
1. Start Enshrouded and set its mouse sensitivity the way you like it.
2. In HeadMouse open **Settings → Game**, press **Test turn in 5 seconds**, and click into the game.
   You can also press **F6** in the game while that tab is open.
3. The camera should turn exactly one full circle. If not, type how far it actually turned (e.g.
   400), press **Fix it**, then **Save**. Repeat until it's right.

## 4. Everyday use (for your father)

1. Double-click **HeadMouse** on the desktop.
2. Start Enshrouded. **Head control turns on automatically** when the game window is active, and
   off when you switch away.
3. Hold **F9** (or the foot pedal) to freeze the camera, e.g. to re-center your head.

**Sounds:** rising tone = on, falling tone = off, low double tone = tracking lost (movement
stopped), short high tone = tracking back.

**The main window:**

| Part | Meaning |
|---|---|
| Big coloured card | Green **On**, amber **Frozen**, grey **Off**, red **Can't see your face** / **No tracking**, with a one-line hint underneath |
| Head control switch | Same as F10 |
| Head view | The dot is your head. Green box = dead zone, dashed box = full speed; the arrows light up in the direction the camera is turning |
| Re-center | Look straight at the screen and press it (or F8) |
| Settings | Everything else (below) |
| Camera / Stay on top | Small switches at the bottom: a floating camera preview, and keeping HeadMouse above the game |

**Settings** has four tabs. Changes are tried out immediately; **Save** keeps them and **Undo
changes** goes back.
- **Feel:** pick a direction (Right, Left, Up, Down) and adjust it while watching the graph.
- **Tracking:** webcam or OpenTrack, camera choice, steadiness, the setup wizard, and the OpenTrack
  profile helper.
- **Game:** calibration for the game, and auto-on in the game window. Head control is paused while
  this tab is open.
- **Keys & sound:** click a key slot and press the new key (or tap the foot pedal). Also sound volume
  and Light/Dark/System appearance.

## 5. Keys

| Key | Action |
|---|---|
| **F10** | Head control on/off |
| **F9** (hold) | Freeze camera immediately; release to resume. Overrides everything |
| **F7** (hold) | Precision mode: 80% slower, for aiming |
| **F8** | Re-center (look straight at the screen first) |
| **F6** | Test turn (only while **Settings → Game** is open) |

Change them under **Settings → Keys & sound**: click a key slot, then press the key you want
(or tap the foot pedal). Keys are only *watched*, never blocked, so the game
also receives them. Choose keys the game doesn't use. A foot pedal programmed to send F9 works
exactly like F9.

## 6. Adjusting the feel

### Let HeadMouse find the settings: the practice game

**Settings → Feel → Find my best settings (practice game).** Blue targets appear; steer the
crosshair onto each one with your head, exactly like in the game, and hold it there until it turns
green. The mouse is not moved and head control doesn't need to be on.

- **Round 1** (12 targets, about a minute) uses your current settings. HeadMouse watches how you
  reach the targets in each direction: overshooting, creeping up slowly, holding full tilt for a
  long time, or drifting off the target.
- **Round 2** tries adjusted settings (small, bounded changes).
- With **mouse-like aiming** switched on (see Precise aiming below), one target per direction is a
  small move. Those tune the mouse-like sensitivity (gentler if small moves were jumpy, stronger
  if you had to turn past the mouse-like area to reach them), and overshooting big turns widens the
  blend. The dead zones are left alone, because they set the size of the mouse-like area.
- At the end it shows both times and exactly what changed. **Nothing is kept unless you press
  "Use the new settings"**, and the old settings are backed up even then. If your settings already
  suit you, it says so and changes nothing.

Run it again any time, for example after getting used to the new settings.

### Presets

A preset is a named feel: the four direction settings plus precision speed. Keys, camera, game
and glance settings are never changed by a preset.

- **Switch:** the **Feel** menu on the main window applies a preset straight away. If your current
  feel isn't saved yet, it offers to save it first.
- **Save:** pick **Save current as a preset...** in that menu, or **Save as...** in **Settings →
  Feel**.
- **Try / delete:** in **Settings → Feel**, choosing a preset tries it live (press **Save** to keep
  it). **Delete** removes one of your own presets.
- Built in: **Normal (default)**, **Gentle (slower, smoother)** and **Fast (quicker turns)**.

Presets are small files in the `presets` folder next to the settings file, and updates keep them.

### Adjusting by hand

Open **Settings → Feel** and choose a direction. The graph shows camera speed against head angle,
with a red dot where your head is right now.

| Slider | Effect |
|---|---|
| Head turn for full speed | Smaller = less head movement needed |
| Top speed | Fastest turning |
| Dead zone | How far you can move before the camera starts turning |
| Start delay | Wait this long before turning, in 0.01 s steps (0 = immediately; e.g. 0.2 s for down lets you glance without moving the camera) |
| Slowest speed *(advanced)* | Speed just outside the dead zone |
| Curve *(advanced)* | 1 = even; higher = finer control near center, faster further out |

**Keep left and right the same** (or up and down, when Up/Down is chosen) makes the opposite
direction match and follow every change, including in the setup wizard and the practice game.
**Precision aim speed** sets how slow precision mode is.

### Precise aiming: mouse-like for small moves (optional)

Further down **Settings → Feel**. Switch on **Mouse-like for small moves, joystick for big
turns**:

- **Inside the dead zone** the camera follows your head like a mouse: it moves exactly as far as
  your head does (times the sensitivity) and stays there when you stop. Very small, precise
  aiming, and no drift.
- **Further out** it spins like a joystick, exactly as before, so you can still turn all the
  way around.
- **Left/right sensitivity** and **Up/down sensitivity** (3× by default): camera degrees for
  each degree of head movement. Lower is more precise.
- **Blend into turning** (2° by default): over this many degrees past the dead zone the
  mouse-like movement fades out while the joystick fades in. 0 is a sharp switch.
- The **Dead zone** slider of each direction sets how big the mouse-like area is. Make it bigger
  for more room. The graph shows the joystick part and the mouse-like sensitivity.
- Coming back to the middle after a turn doesn't swing the camera back. Small moves follow
  again once your head has stopped for a moment.
- Hold the pause key (F9) to move your head without moving the camera, like lifting a mouse.
- If **Up/down follows my head** is also on, up/down follows your head everywhere and this
  applies to left/right only.

### Steadier control (optional)

Each helper is off until switched on, and they all work together with mouse-like aiming.

- **Stop when I come back to the middle.** After a turn, once the head is back near the middle
  (even slightly past it), the camera stays still until the head clearly turns again: **Turn
  again by** degrees (2.5° by default) away from where it came to rest. This stops the slow
  drift that otherwise happens when you stop a little off center or overshoot center. It works
  for up/down too. The first turn from rest is unchanged.
- **Follow my posture.** While you rest in the dead zone, the middle slowly moves (over about
  8 s) to where your head actually rests, so leaning or slouching doesn't need the re-center key.
  It never adjusts while you're turning, never moves more than 6°, and the re-center key resets
  it.

### Up and down

Looking up and down has less room than left and right, because you still need to see the
screen. If up/down is hard to control, switch on **Up/down follows my head (like a mouse)**. A
small head tilt then tilts the camera several times as much (**Strength**, 4× by default), and
the camera stays where you leave it, so you never have to hold your head tilted. Hold the pause
key (F9) to move your head back without moving the camera, like lifting a mouse. Left/right
still work like a joystick. The practice game leaves up/down alone in this mode.

Everything is stored in `headmouse_settings.toml` (with explanations). It can also be edited in
Notepad, and changes apply within a second.

### Glancing away (e.g. at the keyboard): optional

**Off unless you switch it on**, under **Settings → Feel → Glancing away → "Pause the camera when
I look away from the screen"**. Then run the setup wizard once so it learns your glances (it adds a
"Glance at your keyboard" step).

When it's on, HeadMouse keeps the camera still while you look away from the screen:
- **Eyes (built-in webcam):** it combines head tilt with eye direction to work out where you're
  looking. Steering while watching the screen keeps your gaze on the screen; looking down at the
  keyboard sends it below, and the camera pauses. Blinks are ignored.
- **Far away:** a head turn well beyond your normal steering range (1.5× the full-speed angle),
  or a very fast turn past full speed, counts as looking away. This works with OpenTrack too.

The status card shows **Looking away** meanwhile. Movement resumes once you look back and your
head has settled. A simpler alternative without eye tracking is a **Start delay** of about 0.2 s
for Down.

### Your settings are safe

- **Every change is backed up.** To go back, use **Settings → Keys & sound → Restore earlier
  settings** (scroll down).
- **Running the setup wizard again doesn't replace your sensitivity** unless you tick "Also update
  my sensitivity" on its last page. It shows the old and new values first.
- **Settings from an older copy of HeadMouse** (installed with the one-line command before the
  installer existed) are offered there as "From the earlier HeadMouse". A fresh install uses them
  automatically.

## 7. Using OpenTrack instead of the webcam tracker

In **Settings → Tracking**:
1. Select **OpenTrack**.
2. Click **Create HeadMouse profile**. This makes a *copy* of your OpenTrack profile, keeping your
   camera and tracker settings, with the output set to HeadMouse (UDP 127.0.0.1:4242) and the
   yaw/pitch curves set to 1:1. Your existing profiles aren't changed.
3. In OpenTrack, pick the **HeadMouse** profile and press **Start**.

With "Start OpenTrack with HeadMouse" ticked, HeadMouse launches OpenTrack for you. You still press
Start in OpenTrack, because it has no auto-start option.

## 8. Safety

HeadMouse stops all movement, rather than guessing, when:
- no tracking data arrives for 0.25 s (face not visible, camera unplugged, OpenTrack closed)
- the data freezes (exactly the same numbers for 1 s)
- the angle jumps more than 25° at once
- the data is impossible

It also stops while F9 is held, while off, and while the wizard or a test turn runs. Leftover
fractions of movement are thrown away on every stop. Direction only reverses after your head has
rested in the dead zone for 0.15 s.

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| "Webcam support is not installed" | Run the install line (or `Setup.bat`) again and watch for errors in step 2. |
| "Camera 0 not found or busy" | Close OpenTrack, Zoom, Teams, etc. Wrong camera? Choose another in **Settings → Tracking**. |
| "Looking for your face" stays red | Face the camera, put light on your face (not behind you), and move closer. |
| Movement is jittery | **Settings → Tracking → Steadiness**: move it left. Or raise the dead zone. |
| Movement feels laggy | Move Steadiness a little to the right. |
| Turns the wrong way | Run the **Setup wizard**; it fixes directions automatically. |
| Camera moves when glancing at the keyboard | Switch on **Settings → Feel → Glancing away** and run the setup wizard, or set the Down **Start delay** to about 0.2 s. |
| Settings changed or lost | **Settings → Keys & sound → Restore earlier settings** (scroll down). |
| Camera pauses while steering normally ("Looking away") | Under **Settings → Feel → Glancing away**, raise "How far below the screen" or "Far away means", or switch the eye check off. |
| Drifts with head centered | Press **Re-center** (F8) while looking straight at the screen. |
| Doesn't turn on in the game | The game's window title must contain "Enshrouded" (`game_window_title` in the settings file). Or just press F10. |
| Shows ACTIVE but the game camera doesn't move | If Enshrouded runs as administrator, Windows silently blocks input from normal programs. Run HeadMouse as administrator too (right-click → Run as administrator). |
| "Webcam support could not load" | Setup installs the Microsoft Visual C++ runtime when needed. If permission was refused, run setup again and click Yes, or install it from <https://aka.ms/vs/17/release/vc_redist.x64.exe>. |
| Speeds feel wrong in game | Redo the calibration in **Settings → Game** after changing the game's mouse sensitivity. |
| F9/F10 also do something in the game | Pick other keys under **Settings → Keys & sound** (e.g. Pause or Scroll Lock). |
| Beeps a lot / stutters in game | Make sure only one HeadMouse is open (since 1.1.2 a second launch just brings the first window forward). The chip at the top shows the tracking rate (e.g. "Webcam · 30/s"); if it drops a lot while the game runs, close other programs or lower the game's graphics settings. |
| Something odd happened | `headmouse.log` in the HeadMouse folder (`%LOCALAPPDATA%\Programs\HeadMouse`) records tracking losses, the tracking rate and on/off changes. |
| HeadMouse closed with an error | See `headmouse_error.log` in the HeadMouse folder (`%LOCALAPPDATA%\HeadMouse` when installed with the one-liner). |
| Windows Firewall asks about Python | Only needed for OpenTrack mode (local only). Allowing *Private networks* is enough. |

## 10. Releasing a new version (developer)

1. Change `__version__` in `headmouse/__init__.py` (e.g. `1.0.1`) and push to `master`.
2. GitHub Actions tests everything on Windows, builds `HeadMouse-Setup.exe`, and, because there's
   no release for that version yet, publishes release `v1.0.1` with the installer attached.
   Installed copies of HeadMouse then offer the update.

Every push also produces the installer as a downloadable artifact on the Actions page.
`build_exe.bat` builds the app locally; `installer/headmouse.iss` is the Inno Setup script.

## 11. For the developer

```
headmouse/tracking.py         OpenTrack UDP input (6 little-endian doubles: X,Y,Z,yaw,pitch,roll)
headmouse/webcam.py           built-in tracking: OpenCV + MediaPipe Face Landmarker, One Euro filter
headmouse/safety.py           decides whether tracking data can be trusted
headmouse/curves.py           head angle -> camera speed for one direction
headmouse/controller.py       joystick logic: dead zones, start delay, no-reverse rule, pause, fractions -> counts
headmouse/glance.py           glance guard: pauses while looking away (gaze from head + eyes, look-away range)
headmouse/engine.py           the loop on a background thread; keys, sounds, auto-on, test turn
headmouse/calibration.py      setup-wizard maths
headmouse/tuning.py           practice game: measures each direction and proposes better settings
headmouse/gui.py              the window (CustomTkinter): main screen, Settings, setup wizard
headmouse/opentrack_setup.py  OpenTrack profile copy/patch and launching
headmouse/winput.py           Windows SendInput / GetAsyncKeyState
headmouse/sounds.py           generated tone cues (winsound)
headmouse/config.py           settings loading, validation, comment-preserving saving, backups, presets
headmouse/updates.py          checks GitHub Releases for a newer version and installs it
headmouse/selfcheck.py        --selfcheck: verifies an installation (used by the build pipeline)
installer/headmouse.iss       Windows installer (Inno Setup)
.github/workflows/windows.yml test, build and release on Windows
tools/fake_opentrack.py       simulated OpenTrack sender for testing
tests/                        py -m unittest -v
```

The other `.bat` files are developer tools: `Monitor tracking.bat` (show tracking data only),
`Dry Run.bat` (window without mouse movement), `Show speed curves.bat`, `Calibrate.bat` (console
calibration) and `Run tests.bat`. `py run_headmouse.py --console` runs without the window.

To run the real-MediaPipe test, set `HEADMOUSE_TEST_ASSETS` to a folder containing
`face_landmarker.task` and a face photo named `portrait.jpg`.

Mouse movement uses `SendInput` with `MOUSEEVENTF_MOVE`, the same call OpenTrack's own mouse output
uses. Nothing is injected into the game process.
