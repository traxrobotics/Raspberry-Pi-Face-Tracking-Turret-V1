"""Shared test setup.

The tests run on any computer, no Pi needed. tests/fakehw stands in for the
camera (spidev, smbus2) and chip select pin (gpiozero), and a temporary folder
stands in for /sys/class/pwm.
"""

import os
import sys
import time
import types

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(HERE, "fakehw"), ROOT]

import cv2  # noqa: E402
import hwstate  # noqa: E402

FACE_IMAGE = os.path.join(HERE, "data", "face.jpg")   # public domain NASA portrait


@pytest.fixture(autouse=True)
def fresh_camera():
    hwstate.reset()
    yield
    hwstate.reset()


@pytest.fixture
def fast_camera(monkeypatch):
    """Skip the camera driver's settle delays, without touching time.sleep anywhere else."""
    import arducam
    real_sleep = time.sleep
    shim = types.SimpleNamespace(sleep=lambda s: real_sleep(min(s, 0.001)), monotonic=time.monotonic)
    monkeypatch.setattr(arducam, "time", shim)
    return arducam


@pytest.fixture
def face_image():
    img = cv2.imread(FACE_IMAGE)
    assert img is not None, "tests/data/face.jpg is missing"
    return img


@pytest.fixture
def fake_pwm(tmp_path):
    """A pretend /sys/class/pwm/pwmchipN for the Pi 5's RP1 PWM0 block."""
    chip = tmp_path / "1f00098000.pwm" / "pwm" / "pwmchip0"
    for ch in (0, 1):
        d = chip / ("pwm%d" % ch)
        d.mkdir(parents=True)
        for f in ("period", "duty_cycle", "enable"):
            (d / f).write_text("0")
    return str(chip)


def servo_angle(chip, channel):
    """Read back the angle a fake servo was last sent (600 to 2400 us = 0 to 180 degrees)."""
    with open(os.path.join(chip, "pwm%d" % channel, "duty_cycle")) as f:
        ns = int(f.read() or 0)
    return 90.0 if ns == 0 else (ns / 1000 - 600) / 1800 * 180


@pytest.fixture
def cfg():
    """A copy of the default config.py settings, safe to change inside one test."""
    import config
    values = {k: getattr(config, k) for k in dir(config) if k.isupper()}
    return types.SimpleNamespace(**values)
