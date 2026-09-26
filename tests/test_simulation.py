"""Whole turret, end to end, in simulation.

The fake camera 'photographs' a big picture with a face in it. Which part of the
picture it sees depends on where the fake servos point, so if the tracker steers
the right way the face slides to the middle, and if it steers wrong it slides off.
"""

import sys

import cv2
import hwstate
import numpy as np
import pytest

from conftest import servo_angle

PX_PER_DEG = 320 / 60.0
FACE_PAN, FACE_TILT = 18.0, -9.0          # where the face really is, degrees from center


@pytest.fixture
def world(make_world):
    return make_world(FACE_PAN, FACE_TILT)


@pytest.fixture
def make_world(face_image, fake_pwm, fast_camera, monkeypatch):
    import config
    import spidev

    monkeypatch.setattr(config, "PWM_CHIP", fake_pwm)
    monkeypatch.setattr(config, "PAN_DIR", 1)
    monkeypatch.setattr(config, "TILT_DIR", 1)
    monkeypatch.setattr(config, "SPI_SPEED_HZ", 8_000_000)

    pad = 900
    src = cv2.resize(face_image, (400, 400))
    canvas = cv2.copyMakeBorder(src, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(40, 40, 40))
    fcx, fcy = 174 + pad, 93 + pad                        # face center in the canvas
    seen = []
    where = {}

    def render():
        ex = (where["pan"] - (servo_angle(fake_pwm, 0) - 90)) * PX_PER_DEG
        ey = (where["tilt"] - (servo_angle(fake_pwm, 1) - 90)) * PX_PER_DEG
        x0, y0 = int(round(fcx - ex - 160)), int(round(fcy - ey - 120))
        frame = canvas[y0:y0 + 240, x0:x0 + 320].copy()
        noise = np.random.default_rng(len(seen)).normal(0, 5, frame.shape)
        frame = np.clip(frame * 0.5 + noise, 0, 255).astype(np.uint8)       # dim, grainy room
        seen.append((ex, ey))
        hwstate.FRAME_JPEG = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])[1].tobytes()

    real_xfer = spidev.SpiDev.xfer2

    def xfer2(self, data):
        if len(data) == 2 and data[0] == 0x84 and data[1] & 0x02:   # capture started
            render()
        return real_xfer(self, data)

    monkeypatch.setattr(spidev.SpiDev, "xfer2", xfer2)

    def make(face_pan, face_tilt):
        where["pan"], where["tilt"] = face_pan, face_tilt
        return seen
    return make


def _run(monkeypatch, frames):
    import time

    import arducam
    import tracker

    real_read = arducam.ArduCam.read
    count = [0]

    def read(self):
        count[0] += 1
        if count[0] > frames:
            raise KeyboardInterrupt
        img = real_read(self)
        time.sleep(0.03)            # a real frame takes time, let the servos move
        return img

    monkeypatch.setattr(arducam.ArduCam, "read", read)
    monkeypatch.setattr(sys, "argv", ["tracker.py", "--no-view"])
    tracker.main()


def test_turret_centers_on_the_face_and_settles(world, monkeypatch):
    import config
    _run(monkeypatch, frames=45)
    start_x = abs(world[0][0])
    assert max(abs(ex) for ex, _ in world) <= start_x + 1, "turret ran away from the face"
    ex, ey = world[-1]
    assert abs(ex) <= config.DEADZONE_X + 4 and abs(ey) <= config.DEADZONE_Y + 4, "did not center"


def test_servos_go_limp_when_stopped(world, monkeypatch, fake_pwm):
    import os
    _run(monkeypatch, frames=10)
    for ch in (0, 1):
        with open(os.path.join(fake_pwm, "pwm%d" % ch, "enable")) as f:
            assert f.read().strip() == "0"


def test_sweeps_to_find_a_face_that_starts_out_of_view(make_world, monkeypatch):
    import config
    monkeypatch.setattr(config, "RETURN_AFTER_S", 0.3)   # start searching quickly
    monkeypatch.setattr(config, "SWEEP_SPEED", 60)
    world = make_world(-40.0, -5.0)                      # far to the left, outside the 60 degree view
    _run(monkeypatch, frames=110)
    assert abs(world[0][0]) > 160, "face should start outside the picture"
    ex, ey = world[-1]
    assert abs(ex) <= config.DEADZONE_X + 4 and abs(ey) <= config.DEADZONE_Y + 4, "never found and centered the face"


# ---------------- a head flicked out of the picture ----------------

@pytest.fixture
def room(face_image, fake_pwm, fast_camera, monkeypatch):
    """A still room with only a head in it. The head can flick sideways with motion blur."""
    import time

    import config
    import spidev

    monkeypatch.setattr(config, "PWM_CHIP", fake_pwm)
    monkeypatch.setattr(config, "PAN_DIR", 1)
    monkeypatch.setattr(config, "TILT_DIR", 1)
    monkeypatch.setattr(config, "AUTO_ROTATE", False, raising=False)

    rng = np.random.default_rng(7)
    walls = cv2.resize(rng.integers(40, 200, (60, 90, 3)).astype(np.uint8), (3600, 2400),
                       interpolation=cv2.INTER_NEAREST)
    walls = cv2.GaussianBlur(walls, (0, 0), 6)
    head = cv2.resize(face_image, (400, 400))[20:180, 90:260]     # head and shoulders
    state = {"t0": None, "prev": None, "flick_at": None, "to": 0.0, "speed": 1.0}
    seen = []

    def head_angle(t):
        if state["flick_at"] is None or t < state["flick_at"]:
            return 0.0
        moved = state["speed"] * (t - state["flick_at"])
        return state["to"] if moved >= abs(state["to"]) else np.copysign(moved, state["to"])

    def render():
        now = time.monotonic()
        if state["t0"] is None:
            state["t0"] = now
        t = now - state["t0"]
        pan, tilt = servo_angle(fake_pwm, 0) - 90, servo_angle(fake_pwm, 1) - 90
        ex, ey = (head_angle(t) - pan) * PX_PER_DEG, (-5 - tilt) * PX_PER_DEG
        cx, cy = 1800 + pan * PX_PER_DEG, 1200 + tilt * PX_PER_DEG
        frame = walls[int(cy) - 120:int(cy) + 120, int(cx) - 160:int(cx) + 160].astype(np.float32)
        layer = np.zeros_like(frame)
        alpha = np.zeros(frame.shape[:2], np.float32)
        hx, hy = int(160 + ex - 84), int(120 + ey - 45)
        x1, y1, x2, y2 = max(0, hx), max(0, hy), min(320, hx + head.shape[1]), min(240, hy + head.shape[0])
        if x2 > x1 and y2 > y1:
            layer[y1:y2, x1:x2] = head[y1 - hy:y2 - hy, x1 - hx:x2 - hx]
            alpha[y1:y2, x1:x2] = 1.0
        if state["prev"] is not None and now > state["prev"][0]:
            smear = int(min(60, abs(ex - state["prev"][1]) / (now - state["prev"][0]) * 0.04))  # 40 ms exposure
            if smear >= 2:
                k = np.zeros((smear, smear), np.float32)
                k[smear // 2, :] = 1.0 / smear
                layer, alpha = cv2.filter2D(layer, -1, k), cv2.filter2D(alpha, -1, k)
        state["prev"] = (now, ex)
        frame = frame * (1 - alpha[..., None]) + layer
        noise = np.random.default_rng(len(seen)).normal(0, 4, frame.shape)
        frame = np.clip(frame * 0.6 + noise, 0, 255).astype(np.uint8)
        seen.append((t, ex))
        hwstate.FRAME_JPEG = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])[1].tobytes()

    real_xfer = spidev.SpiDev.xfer2

    def xfer2(self, data):
        if len(data) == 2 and data[0] == 0x84 and data[1] & 0x02:
            render()
        return real_xfer(self, data)

    monkeypatch.setattr(spidev.SpiDev, "xfer2", xfer2)

    def flick(at, to, speed):
        state.update(flick_at=at, to=to, speed=speed)
        return seen
    return flick


def _run_for(monkeypatch, seconds, frame_time=0.077):
    import time

    import arducam
    import tracker

    real_read = arducam.ArduCam.read
    start = [None]

    def read(self):
        if start[0] is None:
            start[0] = time.monotonic()
        if time.monotonic() - start[0] > seconds:
            raise KeyboardInterrupt
        time.sleep(frame_time)          # a real frame at 8 MHz
        return real_read(self)

    monkeypatch.setattr(arducam.ArduCam, "read", read)
    monkeypatch.setattr(sys, "argv", ["tracker.py", "--no-view"])
    tracker.main()


@pytest.mark.parametrize("to", [-45.0, 45.0])
def test_catches_a_head_flicked_out_of_the_picture(room, monkeypatch, to):
    flick_at, speed = 1.2, 300.0
    seen = room(flick_at, to, speed)
    _run_for(monkeypatch, 3.4)
    done = flick_at + abs(to) / speed
    back = next((t for t, ex in seen if t > done and abs(ex) < 25), None)
    assert back is not None, "never got the face back"
    assert back - flick_at < 1.3, "took %.2f s to get back to the face" % (back - flick_at)
