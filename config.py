"""Every setting for the turret lives here. Change these, not the other files."""

# ---------------- camera (ArduCAM B0067) ----------------
SPI_BUS = 0
SPI_DEVICE = 0
SPI_SPEED_HZ = 8_000_000      # drops to 4 MHz by itself if frames keep failing
CS_GPIO = 17                  # physical pin 11
I2C_BUS = 1                   # pins 3 and 5

FRAME_SIZE = (320, 240)       # also allowed: (160, 120) or (640, 480)

# Picture orientation. The tracker detects a sideways or upside down camera by
# itself and prints the ROTATE value to put here, so it starts the right way up next time.
ROTATE = 0                    # 0, 90, 180 or 270
MIRROR = False                # True if text in the picture reads backwards

# ---------------- servos (SG90 on hardware PWM) ----------------
PWM_CHIP = None               # None = find it automatically, or e.g. "/sys/class/pwm/pwmchip0"
PAN_CHANNEL = 0               # GPIO12, physical pin 32
TILT_CHANNEL = 1              # GPIO13, physical pin 33

PULSE_MIN_US = 600            # pulse for 0 degrees
PULSE_MAX_US = 2400           # pulse for 180 degrees

PAN_CENTER = 90
PAN_MIN = 20                  # never go past these, so the wires cannot wind up
PAN_MAX = 160

TILT_CENTER = 90
TILT_MIN = 50                 # tighten these if the camera hits the frame
TILT_MAX = 130

# Direction. test_servos.py tells you what these should be.
PAN_DIR = -1                  # flip to 1 if the turret turns AWAY from your face
TILT_DIR = 1                  # flip to -1 if it tilts away from your face

# ---------------- motion ----------------
SERVO_SPEED = 550             # degrees per second. SG90 tops out around 600
SERVO_ACCEL = 4500            # how hard it speeds up and brakes. Lower if the Pi reboots when it moves

# ---------------- tracking ----------------
LEAD = 1.0                    # aim ahead of a moving face. 0 = off, 1 = normal
CORRECTION = 0.9              # share of the error fixed per frame. Lower if it swings past you
DEADZONE_X = 20               # pixels. Face this close to center while still = don't move
DEADZONE_Y = 15
RETURN_AFTER_S = 2.0          # seconds with no face before it starts searching

# ---------------- chasing a face that just left the picture ----------------
CHASE = True                  # face vanished at the edge or while moving fast = turn hard that way
CHASE_DEG = 20                # how far past the last sighting to aim (more if it was moving fast)
CHASE_S = 0.7                 # if the chase has not found it by then, start sweeping that way

# ---------------- searching when nobody is there ----------------
SWEEP = True                  # pan slowly side to side to find a face. False = wait at center
SWEEP_SPEED = 30              # degrees per second. Slower finds faces more reliably
SWEEP_MIN = 40                # left and right ends of the sweep (inside PAN_MIN / PAN_MAX)
SWEEP_MAX = 140
SWEEP_TILT = 90               # tilt angle while searching. Lower or raise to match face height

# ---------------- live view in a browser ----------------
STREAM_PORT = 8000
