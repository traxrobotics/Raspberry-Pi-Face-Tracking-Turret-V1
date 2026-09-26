# Changelog

## 1.3.0 (2026-09-24)

Chases a head that leaves the picture.

* When the face vanishes near an edge, while moving fast, or leaving a blur trail, the turret
  turns hard that way at once (`CHASE`, `CHASE_DEG`, `CHASE_S`). If that misses, it sweeps that
  way right away instead of waiting.
* Flick direction comes from the jump between the last two sightings, not just the slower
  0.4 s speed fit, so a one frame flick is caught.
* New motion hint: compares tiny grey copies of consecutive frames to see which way a blurred
  head went.
* Guards against bouncing: only chases off steady sightings, never from a blurry glimpse mid
  swing, and not twice within 1.5 s.
* Faster servo defaults: `SERVO_SPEED` 450 → 550, `SERVO_ACCEL` 3500 → 4500.
* Log and live view show "chasing".

In a still room simulation with motion blur, a head flicked 40 to 50° at up to 400°/s is back in
the middle in 0.3 to 0.8 s. Before, it often sat still for 2 s and then swept, 2.5 to 5 s total.

## 1.2.0 (2026-09-24)

Searches when you leave.

* With no face for `RETURN_AFTER_S` (now 2 s), the turret sweeps slowly side to side instead of
  waiting at center. It heads toward the side you walked off to first.
* New settings: `SWEEP`, `SWEEP_SPEED`, `SWEEP_MIN`, `SWEEP_MAX`, `SWEEP_TILT`. `SWEEP = False`
  brings back the old wait at center behavior.
* The servo loop can now cap its top speed for a single move (`set_target(..., speed=)`).
* Live view shows "searching..." and the log adds "searching" while sweeping.
* New tests, including a simulation where the face starts out of view and has to be found.

## 1.1.0 (2026-09-24)

Faster tracking.

* Camera runs in its own thread, so the next frame is captured while the last one is searched.
* Aims ahead of a moving face (`LEAD`), using its speed over the last 0.4 s.
* Deadzone only applies while you sit still, so it no longer stops and starts while following you.
* Faster servo defaults: `SERVO_SPEED` 250 → 450, `SERVO_ACCEL` 1500 → 3500.
* SPI clock 4 → 8 MHz by default, and drops back to 4 MHz by itself if frames fail.
* Live view skips drawing and JPEG encoding when nobody is watching.
* Orientation recheck backs off once the picture keeps passing.
* Automatic tests with fake hardware, run on every push by GitHub Actions.

In simulation: 9.8 → 11.9 fps, 25° snap 0.20 → 0.13 s, average error on a walking face 4.7° → 1.9°.

## 1.0.0 (2026-09-23)

First release.

* ArduCAM Mini 2MP Plus driver for the Pi 5 (SPI + I2C, no ArduCAM library needed).
* Hardware PWM servos with a 100 Hz smooth motion loop.
* YuNet / SSD / Haar face detection, picked automatically.
* Automatic fix for a sideways or upside down camera.
* Live browser view.
* Start on boot service, `turret` command and `turret doctor`.
