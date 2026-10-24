"""Getting started: the steps that make HeadMouse work well, and which are done.

Plain logic for the guide window; each step names the place in the app that does it.
"""

from dataclasses import dataclass

from .config import MouseSettings, axis_modes


@dataclass
class Step:
    key: str           # also what the window opens: wizard, game, feel, practice, situations, clicks, glance
    title: str
    why: str
    done: bool
    optional: bool = False


def steps(settings):
    s = settings
    return [
        Step("wizard", "Measure your head movement",
             "The setup wizard learns how far you can comfortably turn, so turning never needs a strain.",
             s.general.setup_done),
        Step("game", "Match the game's turning",
             "A test turn in the game tells HeadMouse how much mouse movement makes a full turn.",
             s.mouse.counts_per_360 != MouseSettings().counts_per_360),
        Step("feel", "Choose how your head moves the camera",
             "For exact aiming, \"Mouse + joystick\" (small moves like a mouse, big ones turn) usually works "
             "best. Up & down can also be \"Mouse only\".",
             any(mode != "joystick" for mode in axis_modes(s))),
        Step("practice", "Find your best settings",
             "The practice game measures your aiming and keeps only changes that clearly work better.",
             s.general.checkup_done),
        Step("situations", "A different feel for aiming (optional)",
             "Slow, exact aiming while you hold the aim button, quick turning while you explore.",
             bool(s.situations.aim_preset or s.situations.build_preset or s.situations.menu_preset), optional=True),
        Step("clicks", "Click without the mouse (optional)",
             "A key, foot pedal or face gesture can press the mouse buttons.",
             s.actions.enabled, optional=True),
        Step("glance", "Look at the keyboard without moving the camera (optional)",
             "HeadMouse pauses while you glance away from the screen.",
             s.glance.enabled, optional=True),
    ]


def progress(settings):
    """(done, total) for the steps everyone should do."""
    needed = [step for step in steps(settings) if not step.optional]
    return sum(step.done for step in needed), len(needed)


def next_step(settings):
    return next((step for step in steps(settings) if not step.done and not step.optional), None)
