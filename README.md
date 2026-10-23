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
   model (3.7 MB), runs a self-test, and puts a **HeadMouse** icon on the desktop.

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

**Desktop test:** press **Turn ON** (or F10). The cursor glides while your head is turned and stops
when centered. Hold **F9**: it freezes. Cover the camera: within a second the window turns red
(**NO TRACKING**) and you hear a low double tone.

**Game calibration:** this makes the speeds real in-game degrees per second.
1. Start Enshrouded and set its mouse sensitivity the way you like it.
2. In HeadMouse click **Game calibration**, then **Test turn in 5 seconds**, and click into the game.
   You can also press **F6** while in the game, as long as the calibration window is open.
3. The camera should turn exactly one full circle. If not, type how far it actually turned (e.g.
   400) and click **Correct it**. Repeat until it's right.

## 4. Everyday use (for your father)

1. Double-click **HeadMouse** on the desktop.
2. Start Enshrouded. **Head control turns on automatically** when the game window is active, and
   off when you switch away.
3. Hold **F9** (or the foot pedal) to freeze the camera, e.g. to re-center your head.

**Sounds:** rising tone = on, falling tone = off, low double tone = tracking lost (movement
stopped), short high tone = tracking back.

**The window:**

| Part | Meaning |
|---|---|
| Big coloured bar | Green **ACTIVE**, yellow **PAUSED**, grey **OFF**, red **NO TRACKING** |
| Box with the dot | Where your head is. Green box = dead zone, dashed box = full speed |
| Turn ON / OFF | Same as F10 |
| Re-center | Look straight at the screen and press it (or F8) |
| Setup wizard | Re-measure your comfortable head range |
| Sensitivity | Sliders for each direction, with a live graph |
| Game calibration | Match speeds to the game (section 3) |
| Tracker / OpenTrack | Choose webcam or OpenTrack; set up an OpenTrack profile |
| Keep on top | Keeps the window visible above the game (borderless/windowed mode) |

## 5. Keys

| Key | Action |
|---|---|
| **F10** | Head control on/off |
| **F9** (hold) | Freeze camera immediately; release to resume. Overrides everything |
| **F7** (hold) | Precision mode: 80% slower, for aiming |
| **F8** | Re-center (look straight at the screen first) |
| **F6** | Test turn (only while the Game calibration window is open) |

Change them under **Sensitivity → Other**. Keys are only *watched*, never blocked, so the game
also receives them. Choose keys the game doesn't use. A foot pedal programmed to send F9 works
exactly like F9.

## 6. Adjusting the feel

Open **Sensitivity**. Each tab (Right, Left, Up, Down) has five sliders, and the graph shows the
result, with a red dot where your head is right now. Changes apply immediately so you can try them.
**Save** keeps them; **Cancel changes** goes back.

| Slider | Effect |
|---|---|
| Dead zone | Head angle with no movement |
| Head angle for full speed | Smaller = less head movement needed |
| Slowest speed | Speed just outside the dead zone |
| Top speed | Fastest turning |
| Curve | 1 = even; higher = finer control near center, faster further out |

Use "Copy these settings to …" to make two directions match. The **Other** tab has precision
speed, webcam steadiness (lower = steadier, higher = quicker), sound volume, reverse up/down,
auto-on in the game, and the keys.

Everything is stored in `headmouse_settings.toml` (with explanations). It can also be edited in
Notepad, and changes apply within a second.

## 7. Using OpenTrack instead of the webcam tracker

In **Tracker / OpenTrack**:
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
| "Camera 0 not found or busy" | Close OpenTrack, Zoom, Teams, etc. Wrong camera? Change the number in **Tracker / OpenTrack**. |
| "Looking for your face" stays red | Face the camera, put light on your face (not behind you), and move closer. |
| Movement is jittery | **Sensitivity → Other → Webcam steadiness**: lower it. Or raise the dead zone. |
| Movement feels laggy | Raise webcam steadiness a little. |
| Turns the wrong way | Run the **Setup wizard**; it fixes directions automatically. |
| Drifts with head centered | Press **Re-center** (F8) while looking straight at the screen. |
| Doesn't turn on in the game | The game's window title must contain "Enshrouded" (`game_window_title` in the settings file). Or just press F10. |
| Works on desktop but not in game | If Enshrouded runs as administrator, run HeadMouse as administrator too. HeadMouse shows a warning when Windows refuses. |
| Speeds feel wrong in game | Redo **Game calibration** after changing the game's mouse sensitivity. |
| F9/F10 also do something in the game | Pick other keys under **Sensitivity → Other** (e.g. `PAUSE`, `SCROLLLOCK`). |
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
headmouse/gui.py              the Tkinter window and its dialogs
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
