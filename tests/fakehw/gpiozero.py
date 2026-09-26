"""Fake gpiozero: just enough for the camera chip select line."""

import hwstate


class DigitalOutputDevice:
    def __init__(self, pin, initial_value=False):
        self.pin = pin
        self._set(bool(initial_value))

    def _set(self, high):
        was_low = hwstate.cs_low
        hwstate.cs_low = not high
        if high and was_low:
            hwstate.burst = False  # CS going high ends a burst read

    def on(self):
        self._set(True)

    def off(self):
        self._set(False)

    def close(self):
        pass
