# How it works

## The camera (`arducam.py`)

The ArduCAM Mini 2MP Plus has two parts. The OV2640 sensor is set up over I2C (address 0x30).
The ArduChip stores each JPEG frame in a 384 KB buffer and hands it over on SPI.

ArduCAM's own library does not support the Pi 5, so `arducam.py` follows the same steps
using the normal Linux `spidev` and `smbus2` drivers. Chip select is driven by hand on GPIO17
so it stays low for a whole burst read. The driver cuts the real JPEG out of the buffer by
its start (`FF D8`) and end (`FF D9`) markers, because the buffer starts with a junk byte and
ends with padding. Each frame gets a timestamp for the moment the photo was taken.

## Three loops

```
 camera thread            main loop                       servo loop (100 Hz)
 ─────────────            ─────────                       ───────────────────
 take photo ──frame──▶ find face                          glide toward aim point
 timestamp it          degrees off center                 speed up, cruise, brake
 repeat                where were servos at photo time? ◀── position history
                       how fast is the face moving?
                       new aim point ─────────────────────▶ set_target
```

**Camera thread.** Pulling a frame over SPI is the slowest step. Doing it in its own thread
means the next photo is already on its way while the last one is searched, which gives more
frames per second and fresher frames. If frames keep failing at 8 MHz it drops the SPI clock
to 4 MHz by itself.

**Main loop.** The lens sees about 60° across, so a face 40 pixels off center is a known
number of degrees off. The servos keep moving while a photo is being taken and searched, so
the aim is *where the servos were when the photo was taken*, plus that angle. Using the servo
position at photo time, not the current one, is what stops it from overshooting.

**Leading a moving face.** The main loop fits a straight line through the face's position
over the last 0.4 seconds to get its speed in degrees per second. The face has already moved
on since the photo was taken, so the aim is pushed ahead by speed × (photo age + servo catch
up time), capped at 12°. Speeds under 8°/s count as sitting still, so a box that wobbles by a
pixel never causes twitching. While the servos themselves are snapping fast, their position
at photo time is too uncertain to judge speed from, so leading pauses until they slow down.

**Servo loop.** 100 times a second, each servo moves toward its aim with a trapezoid speed
profile: speed up at `SERVO_ACCEL`, cruise at `SERVO_SPEED`, and brake just in time to land
exactly on target. This keeps motion smooth even though new aim points only arrive about
12 times a second.

## Chasing a face that just left

A head moved fast enough blurs out of the picture in one or two frames. When the face
vanishes, the tracker asks three questions about its last sighting, in order:

1. **Was it moving fast?** Speed from the 0.4 s fit, or from the jump between the last two
   sightings (a sudden flick often shows up in just one frame). Over 25°/s counts.
2. **Was it near the edge?** Face center in the outer part of the picture.
3. **Did something smear away?** `motion_hint` compares a tiny 80×60 grey copy of this frame
   with the one before and finds the middle of the changed pixels. A flicked head leaves its
   blur on the side it went. Only left/right is used: the body sits below the face, so the
   changed area always leans down. If under 0.4% or over 40% of the picture changed (nothing,
   or a light/exposure change), the hint is ignored.

The first clear answer gives the direction. The turret aims `CHASE_DEG` (more if the face was
fast) past the last sighting at full speed. If nothing turns up within `CHASE_S`, it starts
sweeping that way at once instead of waiting.

To stop chases from bouncing back and forth, a chase only starts from a sighting taken
while the servos were fairly still, after the face had been tracked for at least 0.3 s, and
not within 1.5 s of the last chase. A face that vanishes from the middle with none of the
three clues (someone turning away) gets the normal wait, then the sweep.

## Searching

After `RETURN_AFTER_S` seconds with no face, the tracker switches to a sweep. It aims at one
end of the sweep (`SWEEP_MIN` or `SWEEP_MAX`), starting with the side the face was last seen
on, and asks the servo loop to cap its speed at `SWEEP_SPEED` for that move. When the servos
get within 2° of that end, it aims at the other end. Tilt holds at `SWEEP_TILT`.

The speed cap matters: at full speed the camera would smear past a face between frames.
At 30°/s and about 12 frames a second the view moves under 3° per frame, so a face is in view
for about 20 frames on every pass. The moment a face is found, the cap is lifted and normal
tracking takes over at full speed.

## Face detection

`FaceDetector` picks the best model the Pi can run:

| Detector | Needs | Notes |
|---|---|---|
| YuNet | OpenCV 4.8+ (Raspberry Pi OS Trixie) | small, fast, handles angles and dim light |
| SSD (res10) | any OpenCV 4 (Bookworm) | very reliable, a bit slower |
| Haar | nothing | last resort if `models/` is missing |

When there are several faces it sticks with the one closest to the face it was already
following, so it does not jump between people.

## Auto orientation

A face detector is always most confident about an upright face. `AutoOrient` scores the
picture as is and turned 90°, 180° and 270°, and keeps whichever it is surest about. The
servos hold still until the check passes, so they never chase an upside down face (which
would make the turret run away). Once the picture keeps passing, it checks less and less
often, down to once every 320 face frames.

## Servos (`servo.py`)

Hardware PWM through `/sys/class/pwm` at 50 Hz, 600 to 2400 µs for 0 to 180°. The PWM block's
number changes between OS versions, so it is found by name: the one at `...98000.pwm` drives
GPIO12/13. The one at `...9c000.pwm` runs the Pi 5 cooling fan and is never touched.

## Boot service

`install_boot.sh` installs a normal systemd service that runs as root (so it never trips over
permissions at boot) and restarts every 3 seconds until the camera and servos are ready. A
sudoers rule lets your user start and stop exactly that service, and nothing else, with no
password. On stop it glides both servos to center and turns the PWM off so they go limp.
