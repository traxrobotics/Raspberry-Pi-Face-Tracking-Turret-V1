"""Laser pointer control.

The laser is mounted tilted down in its bracket (see docs/wiring.md), so even though the
code below fires it whenever a face is being tracked, the beam lands below your chin, never
at eye height. The code never aims this at a face on its own, and must never be changed to
try to: the safety here comes entirely from the fixed downward tilt built into the mount,
not from anything computed in software. All this does is turn the beam on when a face is
being tracked and off otherwise.

Most small 3 pin laser modules (VCC, GND, S) have their own driver circuit on the S pin, so
a Pi GPIO pin only needs to supply a logic level on/off signal, the same way arducam.py
drives the camera's chip select pin.
"""

import gpiozero


class LaserError(RuntimeError):
    pass


class Laser:
    def __init__(self, gpio):
        try:
            self.pin = gpiozero.DigitalOutputDevice(gpio, initial_value=False)
        except Exception as e:
            raise LaserError(f"Could not use GPIO{gpio} for the laser: {e}") from e

    def on(self):
        self.pin.on()

    def off(self):
        self.pin.off()

    def close(self):
        """Always turn it off before letting go of the pin."""
        try:
            self.off()
        finally:
            self.pin.close()


def make_laser(cfg):
    """Returns a Laser, or None if LASER_ENABLED is False in config.py."""
    if not getattr(cfg, "LASER_ENABLED", False):
        return None
    return Laser(cfg.LASER_GPIO)
