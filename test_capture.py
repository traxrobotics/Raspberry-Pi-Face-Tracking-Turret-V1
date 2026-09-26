"""Step 2: take real pictures and measure the frame rate.

    python3 test_capture.py

Saves snapshot.jpg. Open it and check:
  * sideways or upside down?  add  ROTATE = 90, 180 or 270  to config.py
  * text reads backwards?     set MIRROR = True in config.py
"""

import sys
import time

import cv2
import numpy as np

import config
from arducam import ArduCam, CameraError

try:
    cam = ArduCam(config.SPI_BUS, config.SPI_DEVICE, config.SPI_SPEED_HZ,
                  config.CS_GPIO, config.I2C_BUS)
    print("Starting camera at %dx%d..." % config.FRAME_SIZE)
    cam.start(config.FRAME_SIZE)
except CameraError as e:
    print("FAIL:", e)
    sys.exit(1)

try:
    # First few frames are often dark while exposure settles.
    for _ in range(5):
        cam.capture_jpeg()

    good, sizes, times = 0, [], []
    last = None
    for _ in range(20):
        t0 = time.monotonic()
        jpeg = cam.capture_jpeg()
        times.append(time.monotonic() - t0)
        if jpeg:
            img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                good += 1
                sizes.append(len(jpeg))
                last = img

    if last is None:
        print("FAIL: got no usable frames. Try SPI_SPEED_HZ = 2_000_000 and shorter wires.")
        sys.exit(1)

    from tracker import orient
    last = orient(last, config)
    cv2.imwrite("snapshot.jpg", last)

    h, w = last.shape[:2]
    print("OK   %d of 20 frames good" % good)
    print("     size %dx%d, about %d KB per frame" % (w, h, sum(sizes) / len(sizes) / 1024))
    print("     about %.1f frames per second" % (len(times) / sum(times)))
    print("     saved snapshot.jpg, open it and check which way up it is")
    print()
    print("Next: python3 test_servos.py")
finally:
    cam.close()
