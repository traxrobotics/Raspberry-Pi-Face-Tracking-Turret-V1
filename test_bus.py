"""Step 1: prove the camera wiring. No picture yet, just 'is anyone there'.

    python3 test_bus.py
"""

import sys

import config
from arducam import ArduCam, CameraError

try:
    cam = ArduCam(config.SPI_BUS, config.SPI_DEVICE, config.SPI_SPEED_HZ,
                  config.CS_GPIO, config.I2C_BUS)
except CameraError as e:
    print("FAIL:", e)
    sys.exit(1)

ok = True
try:
    cam.reset_chip()
    got = cam.check_spi()
    if got == 0x55:
        print("SPI  OK    wrote 0x55, read 0x55")
    else:
        ok = False
        print("SPI  FAIL  wrote 0x55, read 0x%02X" % got)
        print("     Check MOSI pin 19, MISO pin 21, SCK pin 23, CS pin 11.")
        if got in (0x00, 0xFF):
            print("     Reading all 0s or all 1s usually means MISO or VCC is not connected.")

    try:
        high, low = cam.sensor_id()
        if high == 0x26 and low in (0x41, 0x42):
            print("I2C  OK    OV2640 found, ID 0x%02X 0x%02X" % (high, low))
        else:
            ok = False
            print("I2C  FAIL  got ID 0x%02X 0x%02X, expected 0x26 0x41 or 0x42" % (high, low))
    except OSError:
        ok = False
        print("I2C  FAIL  sensor did not answer")
        print("     Check SDA pin 3, SCL pin 5, VCC pin 1 (3.3V), GND pin 25.")
finally:
    cam.close()

print()
print("All good. Next: python3 test_capture.py" if ok else "Fix the wiring above and run this again.")
sys.exit(0 if ok else 1)
