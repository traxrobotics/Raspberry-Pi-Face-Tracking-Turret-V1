"""Servo control on the Pi 5's hardware PWM (GPIO12 and GPIO13).

Uses the kernel's /sys/class/pwm interface, which is rock steady timing.
Needs this line in /boot/firmware/config.txt (setup.sh adds it):
    dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4
"""

import glob
import math
import os
import threading
import time
from collections import deque

SYSFS_PWM = "/sys/class/pwm"
PERIOD_NS = 20_000_000       # 50 Hz, what hobby servos expect


class ServoError(RuntimeError):
    pass


def _write(path, value):
    try:
        with open(path, "w") as f:
            f.write(str(value))
    except PermissionError:
        raise ServoError("No permission to control the servos without sudo.\n"
                         "Run this once:  bash install_boot.sh   then  sudo reboot")
    except OSError as e:
        raise ServoError("Could not write %s to %s: %s" % (value, path, e))


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def find_pwm_chip(base=SYSFS_PWM):
    """Find the PWM block that drives GPIO12/13 on a Pi 5.

    Its number changes between OS versions (pwmchip0, 1, 2...), so look for
    it by name instead. The one at ...98000.pwm is PWM0 on the RP1 chip.
    The one at ...9c000.pwm runs the cooling fan, never touch that.
    """
    chips = glob.glob(os.path.join(base, "pwmchip*"))
    chips.sort(key=lambda p: int(p.rsplit("pwmchip", 1)[1]))
    if not chips:
        raise ServoError(
            "No PWM found. Add  dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4  "
            "to /boot/firmware/config.txt and reboot.")

    for c in chips:
        if "98000.pwm" in os.path.realpath(c):
            return c

    not_fan = [c for c in chips if "9c000.pwm" not in os.path.realpath(c)]
    if len(not_fan) == 1:
        return not_fan[0]

    listing = "\n".join("  %s -> %s" % (c, os.path.realpath(c)) for c in chips)
    if not not_fan:
        raise ServoError(
            "Only the fan PWM is present, so the servo overlay did not load.\n"
            "Check /boot/firmware/config.txt has the pwm-2chan line under [all], then reboot.\n" + listing)
    raise ServoError(
        "Found several PWM chips and could not tell which one drives GPIO12/13:\n"
        + listing + "\nSet PWM_CHIP in config.py to the right one.")


class Servo:
    def __init__(self, chip, channel, min_deg, max_deg,
                 pulse_min_us=600, pulse_max_us=2400):
        self.chip = chip
        self.channel = channel
        self.min_deg = min_deg
        self.max_deg = max_deg
        self.pulse_min_us = pulse_min_us
        self.pulse_max_us = pulse_max_us
        self.path = os.path.join(chip, "pwm%d" % channel)
        self.angle = None
        self.enabled = False

        if not os.path.isdir(self.path):
            _write(os.path.join(chip, "export"), channel)
            # The new folder takes a moment to appear and get its permissions.
            for _ in range(100):
                if os.access(os.path.join(self.path, "period"), os.W_OK):
                    break
                time.sleep(0.02)
            else:
                raise ServoError("pwm%d under %s never became writable.\n"
                                 "Run this once:  bash install_boot.sh   then  sudo reboot" % (channel, chip))

        # Duty to 0 first, in case an old duty is bigger than the new period.
        _write(os.path.join(self.path, "duty_cycle"), 0)
        _write(os.path.join(self.path, "period"), PERIOD_NS)

    def angle_to_ns(self, deg):
        us = self.pulse_min_us + (self.pulse_max_us - self.pulse_min_us) * deg / 180.0
        return int(round(us * 1000))

    def write(self, deg):
        """Move to an angle. Always kept inside min_deg..max_deg."""
        deg = max(self.min_deg, min(self.max_deg, float(deg)))
        deg = round(deg, 1)
        if deg == self.angle and self.enabled:
            return deg
        _write(os.path.join(self.path, "duty_cycle"), self.angle_to_ns(deg))
        if not self.enabled:
            _write(os.path.join(self.path, "enable"), 1)
            self.enabled = True
        self.angle = deg
        return deg

    def glide(self, target, step=1.0, delay=0.02):
        """Move slowly, one small step at a time. Kinder to the Pi's 5V rail."""
        if self.angle is None:
            return self.write(target)
        current = self.angle
        target = max(self.min_deg, min(self.max_deg, float(target)))
        while abs(target - current) > step:
            current += step if target > current else -step
            self.write(current)
            time.sleep(delay)
        return self.write(target)

    def release(self):
        """Stop sending pulses. The servo goes limp."""
        if self.enabled:
            try:
                _write(os.path.join(self.path, "enable"), 0)
            except ServoError:
                pass
            self.enabled = False


class _Axis:
    """One servo's smooth motion: speeds up, cruises, slows down, stops on target."""

    def __init__(self, servo, start, speed, accel):
        self.servo = servo
        self.pos = float(start)
        self.target = float(start)
        self.vel = 0.0
        self.speed = speed
        self.accel = accel
        self.limit = None       # a slower top speed for this move only (used by the search sweep)

    def step(self, dt):
        dist = self.target - self.pos
        if abs(dist) < 0.05 and abs(self.vel) < 5:
            self.pos, self.vel = self.target, 0.0
        else:
            # fastest speed that still lets it brake in time
            top = self.speed if self.limit is None else min(self.speed, self.limit)
            want = math.copysign(min(top, math.sqrt(2 * self.accel * abs(dist))), dist)
            dv = max(-self.accel * dt, min(self.accel * dt, want - self.vel))
            self.vel += dv
            new = self.pos + self.vel * dt
            if (self.target - new) * dist < 0:        # would pass the target, land on it
                new, self.vel = self.target, 0.0
            self.pos = new
        if self.servo is not None:
            self.servo.write(self.pos)


class ServoMover:
    """Moves both servos smoothly in the background, 100 times a second.

    The camera only runs about 10 frames a second. If the servos only moved when a
    new frame arrived, they would jump in steps. Instead the camera just says where
    to aim (set_target) and this loop glides there with smooth speed up and slow down.
    """

    def __init__(self, pan, tilt, pan_start, tilt_start, speed=250.0, accel=1500.0, rate_hz=100):
        self.axes = (_Axis(pan, pan_start, speed, accel), _Axis(tilt, tilt_start, speed, accel))
        self.lock = threading.Lock()
        self.period = 1.0 / rate_hz
        self.running = True
        self.recent = deque(maxlen=int(rate_hz * 2))   # last 2 seconds of (time, pan, tilt)
        self.history = None          # set to a list to record (time, pan, tilt), used for testing
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        last = time.monotonic()
        while self.running:
            time.sleep(self.period)
            now = time.monotonic()
            dt = min(0.05, now - last)
            last = now
            with self.lock:
                for a in self.axes:
                    a.step(dt)
                sample = (now, self.axes[0].pos, self.axes[1].pos)
                self.recent.append(sample)
                if self.history is not None:
                    self.history.append(sample)

    def set_target(self, pan, tilt, speed=None):
        """Aim somewhere. speed = a slower top speed for this move, None = full speed."""
        with self.lock:
            for axis, want in zip(self.axes, (pan, tilt)):
                if axis.servo is not None:
                    want = max(axis.servo.min_deg, min(axis.servo.max_deg, want))
                axis.target = float(want)
                axis.limit = speed

    def position(self):
        """Where the servos are right now (not where they are heading)."""
        with self.lock:
            return self.axes[0].pos, self.axes[1].pos

    def position_at(self, when):
        """Where the servos were at an earlier moment (used to match a photo to its angle)."""
        with self.lock:
            if when is None or not self.recent:
                return self.axes[0].pos, self.axes[1].pos
            samples = list(self.recent)
        if when <= samples[0][0]:
            return samples[0][1], samples[0][2]
        for (t1, p1, q1), (t2, p2, q2) in zip(samples, samples[1:]):
            if t1 <= when <= t2:
                k = (when - t1) / (t2 - t1) if t2 > t1 else 0.0
                return p1 + k * (p2 - p1), q1 + k * (q2 - q1)
        return samples[-1][1], samples[-1][2]

    def settle(self, pan, tilt, timeout=3.0):
        """Glide to a spot and wait until it gets there."""
        self.set_target(pan, tilt)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                done = all(a.pos == a.target and a.vel == 0 for a in self.axes)
            if done:
                return
            time.sleep(0.02)

    def stop(self):
        self.running = False
        self.thread.join(timeout=1)


def make_servos(cfg):
    chip = cfg.PWM_CHIP or find_pwm_chip()
    pan = Servo(chip, cfg.PAN_CHANNEL, cfg.PAN_MIN, cfg.PAN_MAX,
                cfg.PULSE_MIN_US, cfg.PULSE_MAX_US)
    tilt = Servo(chip, cfg.TILT_CHANNEL, cfg.TILT_MIN, cfg.TILT_MAX,
                 cfg.PULSE_MIN_US, cfg.PULSE_MAX_US)
    return chip, pan, tilt
