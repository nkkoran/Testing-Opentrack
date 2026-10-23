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

> **Status:** everything except the Windows-specific parts was tested here: the motion logic, the
> setup wizard, the window, and the built-in tracker on a real face image with Google's MediaPipe.
> Mouse output, key reading and live webcam capture haven't been run on Windows yet. Your first
> run is the real test (section 3).

---

## 1. One-time setup (about 10 minutes)

1. **Install Python** 3.13 from <https://www.python.org/downloads/windows/> (3.11 or newer works).
   In the installer, tick **"Add python.exe to PATH"**.
2. **Get HeadMouse:** on the GitHub page, click **Code → Download ZIP** and extract it, e.g. to
   `C:\HeadMouse`.
3. **Double-click `Setup.bat`.** It installs the webcam tracking (MediaPipe), downloads Google's face
   model (3.7 MB), checks that tracking works on this PC, runs a self-test, and puts a
   **HeadMouse** icon on the desktop. If several Python versions are installed, it uses 3.13
   (then 3.12, 3.11, 3.14).

If OpenTrack is running and using the webcam, close it before using the built-in tracking. Only
one program can use a camera at a time.

## 2. First start: the setup wizard

Double-click **HeadMouse** on the desktop. The first time, the **setup wizard** opens by itself:

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

**Game calibration:** this makes the speeds real in-game degrees per second.
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

Open **Settings → Feel** and choose a direction. The graph shows camera speed against head angle,
with a red dot where your head is right now.

| Slider | Effect |
|---|---|
| Head turn for full speed | Smaller = less head movement needed |
| Top speed | Fastest turning |
| Dead zone | How far you can move before the camera starts turning |
| Slowest speed *(advanced)* | Speed just outside the dead zone |
| Curve *(advanced)* | 1 = even; higher = finer control near center, faster further out |

"Copy these to …" makes the opposite direction match. **Precision aim speed** sets how slow
precision mode is.

Everything is stored in `headmouse_settings.toml` (with explanations). It can also be edited in
Notepad, and changes apply within a second.

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
| "Webcam support is not installed" | Run `Setup.bat` again and watch for errors in step 1. |
| "Camera 0 not found or busy" | Close OpenTrack, Zoom, Teams, etc. Wrong camera? Choose another in **Settings → Tracking**. |
| "Looking for your face" stays red | Face the camera, put light on your face (not behind you), and move closer. |
| Movement is jittery | **Settings → Tracking → Steadiness**: move it left. Or raise the dead zone. |
| Movement feels laggy | Move Steadiness a little to the right. |
| Turns the wrong way | Run the **Setup wizard**; it fixes directions automatically. |
| Drifts with head centered | Press **Re-center** (F8) while looking straight at the screen. |
| Doesn't turn on in the game | The game's window title must contain "Enshrouded" (`game_window_title` in the settings file). Or just press F10. |
| Shows ACTIVE but the game camera doesn't move | If Enshrouded runs as administrator, Windows silently blocks input from normal programs. Run HeadMouse as administrator too (right-click → Run as administrator). |
| "Webcam support could not load" / Setup step 3 fails | Install the Microsoft Visual C++ Redistributable (<https://aka.ms/vs/17/release/vc_redist.x64.exe>), then run `Setup.bat` again. |
| Speeds feel wrong in game | Redo the calibration in **Settings → Game** after changing the game's mouse sensitivity. |
| F9/F10 also do something in the game | Pick other keys under **Settings → Keys & sound** (e.g. Pause or Scroll Lock). |
| HeadMouse closed with an error | See `headmouse_error.log` in the HeadMouse folder. |
| Windows Firewall asks about Python | Only needed for OpenTrack mode (local only). Allowing *Private networks* is enough. |

## 10. Optional: a standalone HeadMouse.exe

`build_exe.bat` builds `dist\HeadMouse\HeadMouse.exe` with PyInstaller. The folder runs on PCs
without Python, and the desktop shortcut is pointed at it. It hasn't been tried yet; if it fails,
keep using the normal shortcut.

## 11. For the developer

```
headmouse/tracking.py         OpenTrack UDP input (6 little-endian doubles: X,Y,Z,yaw,pitch,roll)
headmouse/webcam.py           built-in tracking: OpenCV + MediaPipe Face Landmarker, One Euro filter
headmouse/safety.py           decides whether tracking data can be trusted
headmouse/curves.py           head angle -> camera speed for one direction
headmouse/controller.py       joystick logic: dead zones, no-reverse rule, pause, fractions -> counts
headmouse/engine.py           the loop on a background thread; keys, sounds, auto-on, test turn
headmouse/calibration.py      setup-wizard maths
headmouse/gui.py              the window (CustomTkinter): main screen, Settings, setup wizard
headmouse/opentrack_setup.py  OpenTrack profile copy/patch and launching
headmouse/winput.py           Windows SendInput / GetAsyncKeyState
headmouse/sounds.py           generated tone cues (winsound)
headmouse/config.py           settings loading, validation and comment-preserving saving
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
