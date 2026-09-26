import os

import pytest

import servo
from conftest import servo_angle


def _make_chip(base, block, number):
    real = base / "platform" / block / "pwm" / ("pwmchip%d" % number)
    real.mkdir(parents=True)
    link = base / "class" / ("pwmchip%d" % number)
    link.parent.mkdir(exist_ok=True)
    os.symlink(real, link)
    return str(link)


def test_finds_the_servo_pwm_and_never_the_fan(tmp_path):
    _make_chip(tmp_path, "1f0009c000.pwm", 0)           # cooling fan
    servos = _make_chip(tmp_path, "1f00098000.pwm", 2)  # GPIO12/13
    assert servo.find_pwm_chip(str(tmp_path / "class")) == servos


def test_only_fan_pwm_means_the_overlay_is_missing(tmp_path):
    _make_chip(tmp_path, "1f0009c000.pwm", 0)
    with pytest.raises(servo.ServoError, match="overlay"):
        servo.find_pwm_chip(str(tmp_path / "class"))


def test_angle_to_pulse(fake_pwm):
    s = servo.Servo(fake_pwm, 0, 0, 180, 600, 2400)
    assert s.angle_to_ns(0) == 600_000
    assert s.angle_to_ns(90) == 1_500_000
    assert s.angle_to_ns(180) == 2_400_000


def test_write_stays_inside_limits(fake_pwm):
    s = servo.Servo(fake_pwm, 0, 20, 160)
    assert s.write(5) == 20
    assert s.write(175) == 160
    assert abs(servo_angle(fake_pwm, 0) - 160) < 0.1


def test_release_goes_limp(fake_pwm):
    s = servo.Servo(fake_pwm, 1, 0, 180)
    s.write(90)
    s.release()
    with open(os.path.join(fake_pwm, "pwm1", "enable")) as f:
        assert f.read().strip() == "0"


def _run_axis(start, target, speed=450.0, accel=3500.0, dt=0.01, max_steps=500):
    axis = servo._Axis(None, start, speed, accel)
    axis.target = target
    path = [axis.pos]
    for _ in range(max_steps):
        axis.step(dt)
        path.append(axis.pos)
        if axis.pos == target and axis.vel == 0:
            break
    return axis, path


def test_axis_lands_on_target_without_overshoot():
    axis, path = _run_axis(90, 150)
    assert axis.pos == 150 and axis.vel == 0
    assert max(path) <= 150


def test_axis_respects_top_speed():
    _, path = _run_axis(20, 160, speed=450.0)
    fastest = max(abs(b - a) for a, b in zip(path, path[1:])) / 0.01
    assert fastest <= 450.0 + 1e-6


def test_default_speed_is_quick():
    # A 60 degree turn should take well under a quarter second with the defaults.
    _, path = _run_axis(90, 150)
    assert (len(path) - 1) * 0.01 < 0.25


def test_position_at_interpolates_history():
    mover = servo.ServoMover(None, None, 90, 90)
    try:
        mover.stop()
        mover.recent.clear()
        mover.recent.extend([(1.0, 90.0, 90.0), (1.1, 100.0, 80.0)])
        pan, tilt = mover.position_at(1.05)
        assert pan == pytest.approx(95.0)
        assert tilt == pytest.approx(85.0)
    finally:
        mover.stop()


def test_sweep_speed_cap_slows_one_move():
    axis = servo._Axis(None, 90, 450.0, 3500.0)
    axis.target, axis.limit = 150, 30.0
    path = [axis.pos]
    for _ in range(300):
        axis.step(0.01)
        path.append(axis.pos)
    fastest = max(abs(b - a) for a, b in zip(path, path[1:])) / 0.01
    assert fastest <= 30.0 + 1e-6
    assert path[100] == pytest.approx(90 + 30 * 1.0, abs=1.0)   # 1 s at 30 deg/s
    assert path[-1] == 150                                      # still lands on target


def test_set_target_clears_the_speed_cap():
    mover = servo.ServoMover(None, None, 90, 90)
    try:
        mover.set_target(150, 90, speed=30.0)
        assert all(a.limit == 30.0 for a in mover.axes)
        mover.set_target(100, 90)
        assert all(a.limit is None for a in mover.axes)
    finally:
        mover.stop()
