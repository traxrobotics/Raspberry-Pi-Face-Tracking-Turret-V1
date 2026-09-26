import random

import pytest

import tracker

W, H = 320, 240
DEG_PER_PX = 60.0 / W


def face_at_px(cx, cy, size=60):
    return (cx - size / 2, cy - size / 2, size, size, 0.9)


def face_seen_from(pan, tilt, face_pan, face_tilt, cfg):
    """Where a face at (face_pan, face_tilt) degrees shows up in the picture."""
    cx = W / 2 + (face_pan - pan) / DEG_PER_PX * cfg.PAN_DIR
    cy = H / 2 + (face_tilt - tilt) / DEG_PER_PX * cfg.TILT_DIR
    return face_at_px(cx, cy)


def test_aims_at_a_face_right_of_center(cfg):
    cfg.PAN_DIR = 1
    t = tracker.Tracker(cfg)
    pan, tilt = t.update(face_at_px(W / 2 + 80, H / 2), W, H, 90, 90, now=10.0)
    assert pan == pytest.approx(90 + 80 * DEG_PER_PX * t.correction)
    assert tilt == 90


def test_pan_dir_flips_the_direction(cfg):
    cfg.PAN_DIR = -1
    t = tracker.Tracker(cfg)
    pan, _ = t.update(face_at_px(W / 2 + 80, H / 2), W, H, 90, 90, now=10.0)
    assert pan < 90


def test_holds_still_inside_the_deadzone(cfg):
    t = tracker.Tracker(cfg)
    pan, tilt = t.update(face_at_px(W / 2 + cfg.DEADZONE_X - 2, H / 2 + 3), W, H, 90, 90, now=10.0)
    assert (pan, tilt) == (90, 90)


def test_stays_inside_the_limits(cfg):
    cfg.PAN_DIR = 1
    t = tracker.Tracker(cfg)
    pan, _ = t.update(face_at_px(W - 5, H / 2), W, H, cfg.PAN_MAX, 90, now=10.0)
    assert pan == cfg.PAN_MAX


def test_goes_back_to_center_after_losing_you_when_sweep_is_off(cfg):
    cfg.PAN_DIR = 1
    cfg.SWEEP = False
    t = tracker.Tracker(cfg)
    t.update(face_at_px(W / 2 + 80, H / 2), W, H, 90, 90, now=10.0)
    assert t.update(None, W, H, 105, 90, now=10.0 + cfg.RETURN_AFTER_S / 2)[0] != cfg.PAN_CENTER
    assert t.update(None, W, H, 105, 90, now=10.0 + cfg.RETURN_AFTER_S + 0.1)[0] == cfg.PAN_CENTER


def _walk(cfg, speed, servo_speed=0.0, jitter=0.0, frames=8, dt=0.09, latency=0.09):
    """Face walks at `speed` deg/s while the turret sits at 90. Returns (tracker, last aim, face now)."""
    cfg.PAN_DIR = 1
    rng = random.Random(1)
    t = tracker.Tracker(cfg)
    start = 100.0
    face_pan = start
    pan = 90.0
    for i in range(frames):
        photo = 10.0 + i * dt
        face_pan = start + speed * (photo - 10.0)
        x, y, w, h, s = face_seen_from(90, 90, face_pan, 90, cfg)
        x += rng.uniform(-jitter, jitter)
        pan, _ = t.update((x, y, w, h, s), W, H, 90, 90, now=photo + latency,
                          photo_time=photo, servo_speed=servo_speed)
    return t, pan, face_pan


def test_leads_a_moving_face(cfg):
    t, aim, face_at_photo = _walk(cfg, speed=40.0)
    assert t.vel_pan == pytest.approx(40.0, rel=0.1)
    no_lead = 90 + (face_at_photo - 90) * t.correction
    assert aim > no_lead + 3          # aiming ahead of where the photo saw it
    assert aim - no_lead <= t.MAX_LEAD_DEG


def test_lead_can_be_turned_off(cfg):
    cfg.LEAD = 0.0
    t, aim, face_at_photo = _walk(cfg, speed=40.0)
    assert aim == pytest.approx(90 + (face_at_photo - 90) * t.correction)


def test_no_lead_for_a_face_sitting_still_with_a_wobbly_box(cfg):
    t, aim, face_at_photo = _walk(cfg, speed=0.0, jitter=2.0, frames=12)
    assert abs(t.vel_pan) < t.MIN_LEAD_SPEED
    assert aim == pytest.approx(90 + (face_at_photo - 90) * t.correction, abs=0.5)


def test_no_lead_while_the_servos_snap_fast(cfg):
    t, aim, face_at_photo = _walk(cfg, speed=40.0, servo_speed=400.0)
    assert t.vel_pan == 0.0
    assert aim == pytest.approx(90 + (face_at_photo - 90) * t.correction)


def test_pick_face_sticks_with_the_same_person():
    near = face_at_px(100, 100, 40)
    big = face_at_px(250, 120, 90)
    assert tracker.pick_face([near, big], previous=None) == big
    assert tracker.pick_face([near, big], previous=(105, 98)) == near
    assert tracker.pick_face([], previous=(105, 98)) is None


# ---------------- searching ----------------

def _lose_face(cfg, last_px_x):
    """See a face at last_px_x, then nothing for longer than RETURN_AFTER_S."""
    cfg.PAN_DIR = 1
    t = tracker.Tracker(cfg)
    t.update(face_at_px(last_px_x, H / 2), W, H, 90, 90, now=10.0)
    later = 10.0 + cfg.RETURN_AFTER_S + 0.1
    return t, later


def test_waits_before_searching(cfg):
    t, _ = _lose_face(cfg, W / 2 + 60)
    t.update(None, W, H, 100, 90, now=10.0 + cfg.RETURN_AFTER_S / 2)
    assert not t.sweeping and t.speed_limit is None


def test_searches_toward_the_side_you_left(cfg):
    t, later = _lose_face(cfg, W / 2 + 60)            # you walked off to the right
    pan, tilt = t.update(None, W, H, 100, 90, now=later)
    assert t.sweeping
    assert pan == cfg.SWEEP_MAX and tilt == cfg.SWEEP_TILT
    assert t.speed_limit == cfg.SWEEP_SPEED

    t, later = _lose_face(cfg, W / 2 - 60)            # you walked off to the left
    pan, _ = t.update(None, W, H, 80, 90, now=later)
    assert pan == cfg.SWEEP_MIN


def test_sweep_turns_around_at_each_end(cfg):
    t, later = _lose_face(cfg, W / 2 + 60)
    assert t.update(None, W, H, 120, 90, now=later)[0] == cfg.SWEEP_MAX
    assert t.update(None, W, H, cfg.SWEEP_MAX - 1, 90, now=later + 1)[0] == cfg.SWEEP_MIN
    assert t.update(None, W, H, 100, 90, now=later + 2)[0] == cfg.SWEEP_MIN      # keeps going
    assert t.update(None, W, H, cfg.SWEEP_MIN + 1, 90, now=later + 3)[0] == cfg.SWEEP_MAX


def test_finding_a_face_stops_the_sweep(cfg):
    t, later = _lose_face(cfg, W / 2 + 60)
    t.update(None, W, H, 120, 90, now=later)
    pan, _ = t.update(face_at_px(W / 2 + 80, H / 2), W, H, 120, 90, now=later + 0.1)
    assert not t.sweeping and t.speed_limit is None
    assert pan == pytest.approx(120 + 80 * DEG_PER_PX * t.correction)


def test_sweep_stays_inside_the_pan_limits(cfg):
    cfg.SWEEP_MIN, cfg.SWEEP_MAX = 0, 180
    t = tracker.Tracker(cfg)
    assert t.sweep_min == cfg.PAN_MIN and t.sweep_max == cfg.PAN_MAX


# ---------------- chasing a face that leaves the picture ----------------

def _steady_then(cfg, last_px_x, frames=6, dt=0.08):
    """Face sits centered for a while (turret still), then shows up at last_px_x."""
    cfg.PAN_DIR = 1
    t = tracker.Tracker(cfg)
    photo = 10.0
    for _ in range(frames):
        t.update(face_at_px(W / 2 + 1, H / 2), W, H, 90, 90, now=photo + 0.05, photo_time=photo)
        photo += dt
    t.update(face_at_px(last_px_x, H / 2), W, H, 90, 90, now=photo + 0.05, photo_time=photo)
    return t, photo + dt


def _lost(t, when, motion=None):
    return t.update(None, W, H, 90, 90, now=when + 0.05, photo_time=when, motion=motion)


def test_chases_a_face_that_leaves_over_the_edge(cfg):
    t, when = _steady_then(cfg, W - 20, dt=0.3)        # slow drift, last seen at the right edge
    last = t.last_ang[0]
    pan, _ = _lost(t, when)
    assert t.chasing and t.speed_limit is None
    assert pan >= last + cfg.CHASE_DEG - 0.01


def test_chases_the_way_a_fast_flick_went(cfg):
    t, when = _steady_then(cfg, W / 2 - 45)            # one frame: jumped 45 px left
    assert t.jump[0] < -t.CHASE_SPEED
    pan, _ = _lost(t, when)
    assert t.chasing and pan < 90 - cfg.CHASE_DEG + 5


def test_follows_the_motion_smear_when_there_is_no_other_clue(cfg):
    t, when = _steady_then(cfg, W / 2 + 1)
    pan, tilt = _lost(t, when, motion=(60.0, 35.0))    # changed pixels off to the right (and low)
    assert t.chasing and pan > 90 + cfg.CHASE_DEG - 1
    assert tilt == 90                                  # up/down from the smear is not trusted


def test_waits_when_a_face_vanishes_from_the_middle_with_no_clue(cfg):
    t, when = _steady_then(cfg, W / 2 + 1)
    pan, tilt = _lost(t, when, motion=(3.0, 20.0))
    assert not t.chasing and (pan, tilt) == (90, 90)


def test_no_chase_off_a_glimpse(cfg):
    cfg.PAN_DIR = 1
    t = tracker.Tracker(cfg)
    t.update(face_at_px(W - 20, H / 2), W, H, 90, 90, now=10.05, photo_time=10.0)   # seen once, at the edge
    pan, _ = _lost(t, 10.08)
    assert not t.chasing and pan == pytest.approx(t.pan)


def test_no_chase_off_a_sighting_taken_mid_swing(cfg):
    cfg.PAN_DIR = 1
    t, when = _steady_then(cfg, W / 2 + 1)
    t.update(face_at_px(W - 20, H / 2), W, H, 90, 90, now=when + 0.05, photo_time=when, servo_speed=400)
    _lost(t, when + 0.08)
    assert not t.chasing


def test_sweeps_that_way_right_after_a_chase_misses(cfg):
    t, when = _steady_then(cfg, W / 2 - 45)
    _lost(t, when)
    assert t.chasing
    pan, _ = t.update(None, W, H, 60, 90, now=when + cfg.CHASE_S + 0.1, photo_time=when + cfg.CHASE_S)
    assert not t.chasing and t.sweeping
    assert pan == cfg.SWEEP_MIN and t.speed_limit == cfg.SWEEP_SPEED


def test_chase_can_be_turned_off(cfg):
    cfg.CHASE = False
    t, when = _steady_then(cfg, W / 2 - 45)
    _lost(t, when)
    assert not t.chasing


def test_motion_hint_finds_the_smear():
    import numpy as np
    before = np.full((60, 80), 100, np.uint8)
    after = before.copy()
    after[20:40, 50:70] = 200                          # something changed on the right
    dx, dy = tracker.motion_hint(before, after, 160, 120, 320, 240)
    assert dx > 60
    assert tracker.motion_hint(before, before, 160, 120, 320, 240) is None           # nothing moved
    assert tracker.motion_hint(before, before + 80, 160, 120, 320, 240) is None      # whole picture changed
