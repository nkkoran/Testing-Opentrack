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
| Getting started | A checklist of the steps that make HeadMouse fit you, ticked off as they're done, each with a button that goes there |
| Quick fixes | Say what feels wrong ("small aiming is jumpy", "keeps moving after I stop"...) and HeadMouse adjusts it (below) |
| Settings | Everything else (below) |
| Camera / Stay on top | Small switches at the bottom: a floating camera preview, and keeping HeadMouse above the game |

**Settings** has six tabs. Changes are tried out immediately; **Save** keeps them and **Undo
changes** goes back.
- **Feel:** choose **Left & right** or **Up & down**, how the head moves the camera there, and
  the settings for that, while watching the graph.
- **Situations:** a different feel while aiming, building or in menus (below).
- **Clicks:** mouse buttons from a key, a foot pedal or a face gesture (below).
- **Tracking:** webcam or OpenTrack, camera choice, the setup wizard, and the OpenTrack profile
  helper.
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

### Quick fixes: just say what feels wrong

**Quick fixes** (main window, or **Settings → Feel**) lists problems in plain words for left &
right or up & down: big turns too slow or too fast, small aiming jumpy or sticky, shaky when
holding still, laggy, keeps moving after stopping, turning starts during small aiming, and (up &
down) glancing at the keyboard moves the camera. Tap one and HeadMouse makes a small change for
that pair, in the mode it uses, and shows exactly what changed. It is used and saved straight
away: try it in the game, tap again if it needs more, or **Undo last change**. With Situations
set up, first choose **which feel is wrong** (Normal, Aiming, Building, Menus): a fix for the
aiming feel goes into the aiming preset, not your normal feel.

### Let HeadMouse find the settings: the practice game

**Settings → Feel → Find my best settings (practice game).** Steer the crosshair onto each target
with your head, exactly like in the game, and hold it there until it turns green. The mouse is
not moved and head control doesn't need to be on. Choose what to practise:

- **Small aiming** (about 3 minutes): small targets a few degrees away, in all directions. Short
  blocks of 8 targets: first your settings, then a little less and a little more sensitivity,
  then slow-movement precision switched on (or off). Each block is scored by *throughput*
  (aiming difficulty handled per second, from where the crosshair actually stopped, so fast but
  sloppy doesn't win) and by how many targets were hit. The first 2 targets of each block are
  warm-up. A variation is only kept if it clearly beats the best so far, and the winner is
  measured once more at the end, so one lucky block can't decide. If most targets are missed, a
  much calmer setting is tried first. In Joystick mode the slowest speed is varied instead.
- **Up & down** (about 1½ minutes): small targets straight up or down, to tune the up/down
  sensitivity on its own, because looking up and down has less room than left and right.
  Left & right stays as it is.
- **Big turns** (about 1 minute): far targets; overshooting, slow approaches and so on suggest an
  adjustment, which is then tried and kept only if it's faster.
- **Hold steady** (part of Everything and Small aiming): hold the crosshair still in a circle for 3
  seconds. If it wobbles, the wobble filter and steadiness go up a little.
- **Everything** (about 6 minutes) does all of these.

Blocks follow each other after a short countdown, so no clicking is needed. At the end HeadMouse
shows the scores before and after, exactly what would change, and what it tried. **Nothing is kept
unless you press "Use the new settings"**, and the old settings are backed up even then.
Situations are paused during practice. With Situations set up you can also choose to practise
with, and tune, your **Aiming**, **Building** or **Menus** feel; the result then goes into that
feel's preset.

### Presets

A preset is a named feel: the four direction settings, precision speed, and how the head moves
the camera (the mode and the mouse-like settings). Keys, camera, game, glance and the "for all
directions" helpers are never changed by a preset. The built-in presets, and presets saved by
versions before 1.7, keep your current mouse-like settings.

- **Switch:** the **Feel** menu on the main window applies a preset straight away. If your current
  feel isn't saved yet, it offers to save it first.
- **Save:** pick **Save current as a preset...** in that menu, or **Save as...** in **Settings →
  Feel**.
- **Try / delete:** in **Settings → Feel**, choosing a preset tries it live (press **Save** to keep
  it). **Delete** removes one of your own presets.
- Built in: **Normal (default)**, **Gentle (slower, smoother)** and **Fast (quicker turns)**.

Presets are small files in the `presets` folder next to the settings file, and updates keep them.

### Adjusting by hand

**Settings → Feel** shows one pair of directions at a time: **Left & right** or **Up & down**.
Each pair has its own mode and its own settings, so up/down can stay exactly as it is while you
change left/right. The graph shows both directions: camera speed against head angle, the middle
area in green, and a red dot where your head is now.

**1. How your head moves the camera** (choose one for each pair):

| Mode | What it does |
|---|---|
| **Joystick** | Turn past the dead zone and the camera keeps turning; further = faster. Back in the middle, it stops. (The original behaviour.) |
| **Mouse + joystick** | Small head movements move the camera like a mouse: exactly as far as you move, and it stays there. Turn further than the mouse-like area and it keeps turning like a joystick. |
| **Mouse only** *(up & down)* | The camera follows your head like a mouse all the way and never keeps turning by itself. Hold F9 to move your head back without moving the camera. |

**2. Same settings for both sides.** When on, right and left (or up and down) share their
settings and every change goes to both. When off, **Settings for Right / Left** chooses which side
the sliders change.

**3. Only the settings the mode uses are shown:**

| Section | Setting | What it does | Range |
|---|---|---|---|
| Mouse-like movement | Mouse-like area | How far your head can move before the joystick takes over (per side) | 0–20° |
| | Sensitivity | Camera degrees per degree of head movement. Lower = more precise. The slider gives the low values the most room | 0.1–10× |
| | Slow-movement precision | Slow head movements turn the camera only this share of the sensitivity (like mouse acceleration), so small corrections are finer. 100% = off | 10–100% |
| | Full sensitivity from | Head speed where the full sensitivity is reached, so quick moves still cover distance | 2–90°/s |
| | Wobble filter | Head movement smaller than this is ignored as jitter. Smaller = fine corrections (and changes of direction) respond sooner; bigger = steadier when holding still | 0.05–1.5° |
| | Start delay | A movement from rest waits this long, then the camera catches up. A quick glance that comes back sooner is ignored | 0–1 s |
| Joystick turning | Dead zone *(Joystick mode)* | How far you can move before turning starts (per side) | 0–20° |
| | Blend from mouse-like *(Mouse + joystick)* | Over this many degrees past the mouse-like area, mouse-like movement fades out while turning fades in. 0 = sharp switch | 0–10° |
| | Start delay | Wait this long before turning, so a quick glance past the edge doesn't turn | 0–2 s |
| | Head turn for full speed | Smaller = less head turn needed for top speed | 3–60° |
| | Top speed | Fastest turning | 10–720°/s |
| | Slowest speed | Speed where turning starts | 0–120°/s |
| | Curve | 1 = even; higher = gentler at first, faster further out | 0.5–6 |
| Steadiness | Steadiness | Smooths tracking jitter for this pair. Left = steadier, right = quicker (less lag). Built-in webcam only | |

The two **Start delay** settings are separate on purpose. The mouse-like one protects small
aiming from glances; the joystick one stops quick glances past the edge from turning the camera.

**Aiming precisely.** A head can't hold as still as a hand, and webcam tracking wobbles by a few
tenths of a degree, so small aiming is about making slow, small head movements turn the camera
very little while quick moves still go far. Try, one at a time:
1. **Mouse + joystick**, with a lower **Sensitivity** (try 1× or below).
2. **Slow-movement precision** around 40%.
3. **Wobble filter** around 0.15°, if small corrections feel sticky (raise it if aim shakes).
4. **Precision aim** (F7, or tap mode) for shots that need it.
5. A bigger **Mouse-like area**, so the joystick doesn't take over during fine aiming.
6. Good, even light on the face makes the webcam wobble less than any setting can.

**Too smooth or slow to respond?** Try these one at a time: move **Steadiness** right, lower
**Curve**, lower **Blend from mouse-like**, raise **Sensitivity**.
**Too jumpy?** The other way round.

**4. For all directions** (further down, each off until switched on):

- **Precision aim speed:** camera speed while the precision key (F7) is held. Switch on **Tap F7
  to switch precision aim on and off** if holding a key is awkward: a falling beep means precision
  aim is on, a rising beep means it's off. It works in every mode.
- **Stop when I come back to the middle (joystick).** After a joystick turn, once the head is back
  near the middle (even slightly past it), the camera stays still until the head clearly turns
  again: **Turn again by** degrees away from where it came to rest. Stops slow creeping.
- **Follow my posture.** While you rest in the middle, the middle slowly moves (over about 8 s) to
  where your head actually rests, so leaning or slouching doesn't need the re-center key. Never
  while turning, never more than 6°, and the re-center key resets it.

**Mouse + joystick details.** Coming back to the middle after a turn doesn't swing the camera
back. Small movements follow again as soon as your head reaches the middle or stops for a moment.
While this mode is on, the setup wizard and the practice game never make the mouse-like area
smaller.

Everything is stored in `headmouse_settings.toml` (with explanations). It can also be edited in
Notepad, and changes apply within a second. Settings saved by earlier versions keep working
unchanged.

### Situations: a different feel for aiming, building and menus

Different parts of the game want different movement: quick turning while exploring, slow and
exact while aiming a bow or placing a building piece, and a pointer in menus. **Settings →
Situations** has one card for each:

- **Feel:** the preset to use. **Make suggested** creates a starting preset from your current
  settings (mouse-like, lower sensitivity, slow-movement precision; a bigger mouse-like area for
  menus) that you can then fine-tune on the Feel tab.
- **Key:** the key or mouse button **the game** uses for it. HeadMouse only watches it. **Hold**
  uses the feel while the key is held; **Tap on/off** switches it on and off. In Enshrouded you
  aim a bow by holding the right mouse button (or Q), so aiming defaults to RIGHTMOUSE + Hold.
  For building, choose a key the game doesn't use and tap it when you start and stop.
- **Menus:** also **when the game shows a mouse pointer**: HeadMouse switches whenever Windows
  shows a pointer in the game window. Whether Enshrouded uses the Windows pointer isn't known for
  sure; the tab shows "mouse pointer shown/hidden" live so you can check in a menu. If it doesn't
  change, use a key instead.
- If two are active, menus win over aiming, aiming over building. A short blip plays on each change
  (can be switched off), and the main window shows which feel is in use. Turning head control off
  and on goes back to the normal feel.

### Clicking without the mouse: keys, a foot pedal or face gestures

**Settings → Clicks**, off until **Use click actions** is switched on. For playing with one hand on
the keyboard:

- **Keys or a foot pedal** (up to three): the key acts as a mouse button. The game still receives
  the key, so choose one it doesn't use, or a foot pedal.
- **Face gestures** (built-in webcam): **open mouth**, **raise eyebrows**, **smile**, **pucker
  lips**, in the style of Google's Project Gameface. Each has a live bar showing how strongly
  the webcam sees it, and a **Counts from** slider. Make the gesture a few times and set the
  slider a little below your usual peak, high enough that talking doesn't reach it. Easier:
  **Measure my gestures** asks you to relax, then make each gesture and hold it (about 20
  seconds), and sets each slider halfway between your relaxed face and the gesture. It also says
  which gestures the webcam sees clearly and which are hard to see. A gesture
  must be held for **Hold the gesture for** (0.15 s) before it counts, and it lets go a little
  below the slider, so it doesn't flicker.
- **What each can do:**
  - hold the left, right or middle button while held (e.g. open mouth = hold right button to
    aim a bow),
  - a single left or right click,
  - left or right button on/off (tap to hold it down, tap again to let go),
  - re-center, precision aim on/off, or freeze the camera on/off.
- **Safety:** buttons are only pressed while head control is on and the game window is in front,
  never during the practice game, and every button is let go when head control turns off or
  HeadMouse closes. The window shows which buttons HeadMouse is holding.
- A held right button should also count as the aiming key for **Situations**, so "open mouth to
  aim" can switch to the aiming feel too. Check that the Situations tab shows Aiming while you
  hold the gesture.
- Opening the mouth tilts the face a little, which would nudge the aim as you click. So
  **Keep the aim still while a gesture starts or ends** holds the camera for a moment then (at
  most 0.3 s while a gesture might be starting, so talking doesn't keep it paused). Switch it off if
  the camera pauses while you talk. Eyebrows or a key are steadier still for precise shots.

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
| Movement is jittery | **Settings → Feel → Steadiness** (for that pair): move it left. Or raise the dead zone. |
| Movement feels laggy or too smooth | Move Steadiness a little to the right; see "Too smooth or slow to respond?" above. |
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
headmouse/quickfix.py         Quick fixes: plain-language problems -> small, bounded setting changes
headmouse/situations.py       Situations: descriptions and suggested feels (aiming, building, menus)
headmouse/practice.py         practice check-up: blocks, throughput scoring, trying and confirming variations
headmouse/actions.py          click actions: gestures (smoothing, threshold, hold) and key/gesture -> buttons
headmouse/guide.py            Getting started steps and which are done
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
