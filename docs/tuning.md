# Tuning

All settings are in `config.py`. After a change, run `turret restart`.

| Problem | Change |
|---|---|
| Turret runs away from your face | flip the sign of `PAN_DIR` or `TILT_DIR` |
| Swings past your face, then comes back | `CORRECTION = 0.75` (default 0.9) |
| Stops a little short of your face | `CORRECTION = 1.0` |
| Falls behind when you walk | `LEAD = 1.3` (default 1.0) |
| Overshoots when you stop walking | `LEAD = 0.6`, or `0` to turn leading off |
| Moves too slowly | `SERVO_SPEED = 600` (default 550, SG90 tops out near here) |
| Starts and stops too sharply | `SERVO_ACCEL = 2500` (default 4500) |
| Loses you when you whip your head away | check `CHASE = True`, raise `CHASE_DEG` to 25 |
| Chases off when you only turn your head | `CHASE_DEG = 12`, or `CHASE = False` |
| Pi reboots when the servos move | add the 1000 µF cap, then `SERVO_ACCEL = 1500` |
| Twitches even when you sit still | raise `DEADZONE_X` / `DEADZONE_Y` |
| You swapped the lens | `FOV_DEG = ` its horizontal angle (stock lens is 60) |
| Camera hits the frame | tighten `TILT_MIN` / `TILT_MAX` |
| Frames keep failing | `SPI_SPEED_HZ = 4_000_000` (it also drops there by itself) |
| Low frame rate | `FRAME_SIZE = (160, 120)` |
| Misses you when you are far away | `FRAME_SIZE = (640, 480)` (slower, sees farther) |
| Locks onto things that are not faces | `FACE_SCORE = 0.75` (default 0.6 YuNet, 0.5 SSD) |
| Box flickers off too often | `HOLD_FACE_S = 1.0` (default 0.5) |
| Sweeps right past you without stopping | `SWEEP_SPEED = 20` (default 30) |
| Searches too high or too low | change `SWEEP_TILT` (default 90) |
| Hits something or pulls wires while searching | narrow `SWEEP_MIN` / `SWEEP_MAX` |
| Starts searching too soon or too late | `RETURN_AFTER_S` (default 2.0) |
| Rather it wait at center than search | `SWEEP = False` |
| Auto rotate guesses wrong | `AUTO_ROTATE = False` and set `ROTATE` yourself |

## Speed, in numbers

Measured in the built in simulator (fake camera at a realistic frame time, face jumping
25° and then walking side to side at up to about 50°/s):

| | v1.0 | v1.1 |
|---|---|---|
| Frames per second | 9.8 | 11.9 |
| Time to snap onto a face 25° away | 0.20 s | 0.13 s |
| Average aim error on a walking face | 4.7° | 1.9° |

Real numbers on your Pi depend on wire length (SPI speed) and your OpenCV version.
Watch `turret log`, it prints the frame rate every 2 seconds.

## Settings that are no longer used

`GAIN`, `MAX_STEP`, `SMOOTHING` and `ROTATE_180` from old configs are ignored
(`ROTATE_180 = True` still works and means `ROTATE = 180`). Delete them whenever you like.
