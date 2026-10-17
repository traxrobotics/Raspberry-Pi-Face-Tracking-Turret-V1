"""Fake gpiozero: the camera chip select line, plus any other plain on/off pin (laser)."""

import hwstate

try:
    import config
    CS_GPIO = getattr(config, "CS_GPIO", 17)
except ImportError:
    CS_GPIO = 17


class DigitalOutputDevice:
    def __init__(self, pin, initial_value=False):
        self.pin = pin
        self.value = 0
        self._set(bool(initial_value))

    def _set(self, high):
        self.value = 1 if high else 0
        if self.pin != CS_GPIO:
            return
        was_low = hwstate.cs_low
        hwstate.cs_low = not high
        if high and was_low:
            hwstate.burst = False  # CS going high ends a burst read

    @property
    def is_active(self):
        return bool(self.value)

    def on(self):
        self._set(True)

    def off(self):
        self._set(False)

    def close(self):
        pass
