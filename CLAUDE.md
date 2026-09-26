# CLAUDE.md

Context for Claude Code when working in this repo.

## What this is

A face tracking pan and tilt turret on a Raspberry Pi 5. ArduCAM Mini 2MP Plus (B0067, OV2640)
over SPI + I2C, two SG90 servos on hardware PWM (GPIO12 pan, GPIO13 tilt). Python 3.11+, OpenCV.
Full wiring in `docs/wiring.md`, internals in `docs/how-it-works.md`.

## Commands

```bash
pip install -r requirements-dev.txt   # once
pytest                                # all automatic tests, no Pi needed, about 10 s
ruff check .                          # lint
shellcheck -S warning setup.sh install_boot.sh doctor.sh turret
```

Run all three before every commit. CI runs the same on every push.

## Layout rules

* `config.py` holds every user setting. Code reads optional settings with
  `getattr(cfg, "NAME", default)` so old config files keep working. Keep doing that for new settings.
* Top level `test_bus.py`, `test_capture.py`, `test_servos.py` are **hardware checks** run by hand
  on the Pi. They run at import, so pytest is limited to `tests/` in `pyproject.toml`. Do not rename
  them, the README and `turret doctor` refer to them by name.
* `tests/fakehw/` fakes `spidev`, `smbus2` and `gpiozero`. `tests/conftest.py` puts it first on
  `sys.path`. The fake camera "takes the photo" when FIFO_START is written, like the real one.
* `tests/test_simulation.py` runs the whole `tracker.main()` against a fake camera whose view
  depends on the fake servo angles. If you change aiming or motion, this is the test that matters.

## Hardware rules (never break these)

* Never touch the PWM block at `...9c000.pwm`. That is the Pi 5 cooling fan. Servos are on `...98000.pwm`.
* Camera VCC is 3.3 V. Never suggest 5 V for the camera.
* Only GPIO 12, 13, 18, 19 have hardware PWM on a Pi 5.
* On stop, servos glide to center and then PWM is disabled (servos go limp). Keep that behavior.

## Searching

When no face is seen for `RETURN_AFTER_S`, `Tracker._sweep_step` aims at the sweep ends and sets
`Tracker.speed_limit`; the main loop passes it to `ServoMover.set_target(..., speed=)`. Any face
clears `sweeping` and `speed_limit`. `tests/test_simulation.py` has a test where the face starts
out of view and must be found by the sweep.

## Chasing

When the face vanishes, `Tracker._start_chase` picks a direction from (1) speed, the 0.4 s fit or
the last two sightings' `jump`, (2) `last_edge`, (3) `motion_hint` (left/right only). Guards:
`last_servo_speed < FAST_SERVO`, tracked for `STEADY_S`, 1.5 s since the last chase. These guards
stop ping-pong; do not remove them without rerunning `test_catches_a_head_flicked_out_of_the_picture`
many times. Note: a sim that moves the whole photo (not just a head) makes `motion_hint` useless;
the still-room `room` fixture is the realistic one.

## Planned, not built

SSD1306 OLED "eyes" on the shared I2C bus (0x3C, camera is 0x30), VCC on pin 17. Do not add it
unless asked. If it is added, keep it optional (off when the screen is not found) and never let
a screen error stop the tracker.

## Threads

Three threads: camera (`FrameGrabber`), main loop, servo motion (`ServoMover`, 100 Hz).
Only the camera thread touches the camera. `ServoMover` state is behind its lock.
Unexpected exceptions in the camera thread are handed to the main loop and re-raised there.

## Style

* User facing messages are plain, short sentences that say which pin or setting to check.
  No jargon, avoid hyphens where a plain word works.
* No new runtime dependencies beyond what `setup.sh` installs with apt.
* Keep functions small and commented in the same plain voice as the rest of the code.
