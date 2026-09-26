"""Step 3: move each servo slowly and work out which way is which.

    python3 test_servos.py

Stand BEHIND the turret, looking the same way the camera looks.
Press Ctrl+C at any time to stop. The servos go limp when it ends.
"""

import sys
import time

import config
from servo import ServoError, make_servos


def ask(question, choices):
    while True:
        answer = input(question).strip().lower()[:1]
        if answer in choices:
            return answer
        print("  type one of: %s" % ", ".join(choices))


try:
    chip, pan, tilt = make_servos(config)
except ServoError as e:
    print("FAIL:", e)
    sys.exit(1)

print("Using PWM at", chip)
print()

try:
    print("Centering pan...")
    pan.write(config.PAN_CENTER)
    time.sleep(0.6)
    print("Centering tilt...")
    tilt.write(config.TILT_CENTER)
    time.sleep(0.6)

    print()
    print("Sweeping pan across its limits (%d to %d)." % (config.PAN_MIN, config.PAN_MAX))
    print("Watch for binding or wires pulling.")
    pan.glide(config.PAN_MIN)
    pan.glide(config.PAN_MAX)
    pan.glide(config.PAN_CENTER)

    print("Sweeping tilt across its limits (%d to %d)." % (config.TILT_MIN, config.TILT_MAX))
    print("If the camera hits anything, tighten TILT_MIN / TILT_MAX.")
    tilt.glide(config.TILT_MIN)
    tilt.glide(config.TILT_MAX)
    tilt.glide(config.TILT_CENTER)

    print()
    print("Direction check. Stand behind the turret, facing where the camera faces.")
    pan.glide(config.PAN_CENTER + 25)
    a = ask("Did the camera turn to the LEFT or RIGHT? [l/r] ", ["l", "r"])
    pan_dir = 1 if a == "r" else -1
    pan.glide(config.PAN_CENTER)

    tilt.glide(config.TILT_CENTER + 20)
    a = ask("Did the camera look UP or DOWN? [u/d] ", ["u", "d"])
    tilt_dir = 1 if a == "d" else -1
    tilt.glide(config.TILT_CENTER)

    print()
    print("Put these two lines in config.py:")
    print()
    print("    PAN_DIR = %d" % pan_dir)
    print("    TILT_DIR = %d" % tilt_dir)
    print()
    print("Next: python3 tracker.py")

except (KeyboardInterrupt, EOFError):
    print("\nStopped.")
finally:
    pan.release()
    tilt.release()
