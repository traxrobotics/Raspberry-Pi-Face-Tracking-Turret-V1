"""Driver for the ArduCAM Mini 2MP Plus (B0067) on a Raspberry Pi 5.

The camera board has two parts:
  * the OV2640 sensor, set up over I2C (address 0x30)
  * the ArduChip, a small chip that stores each frame and hands it over on SPI

This follows the same steps as ArduCAM's own library, but uses the normal
Linux SPI and I2C drivers so it works on a Pi 5.
"""

import time

import spidev
from gpiozero import DigitalOutputDevice

try:
    from smbus2 import SMBus
except ImportError:  # older package name, same functions
    from smbus import SMBus

import ov2640_regs as regs

# ArduChip registers (from ArduCAM.h)
TEST_REG = 0x00
FRAMES_REG = 0x01
FIFO_REG = 0x04
RESET_REG = 0x07
TRIG_REG = 0x41
FIFO_SIZE1 = 0x42
FIFO_SIZE2 = 0x43
FIFO_SIZE3 = 0x44
BURST_FIFO_READ = 0x3C

FIFO_CLEAR = 0x01
FIFO_START = 0x02
CAP_DONE = 0x08
MAX_FIFO_SIZE = 0x5FFFF     # 384 KB on the 2MP Plus

SENSOR_ADDR = 0x30
SPI_CHUNK = 4096            # Linux spidev refuses bigger single transfers by default

SIZE_TABLES = {
    (160, 120): regs.OV2640_160x120_JPEG,
    (320, 240): regs.OV2640_320x240_JPEG,
    (640, 480): regs.OV2640_640x480_JPEG,
}


class CameraError(RuntimeError):
    pass


NO_PERMISSION = ("No permission to use the camera pins without sudo.\n"
                 "Run this once:  bash install_boot.sh   then  sudo reboot")


def extract_jpeg(buf):
    """Cut the real JPEG out of the raw FIFO data.

    The FIFO can start with a junk byte and end with padding, so find the
    start marker (FF D8) and the end marker (FF D9) and keep what is between.
    """
    start = buf.find(b"\xff\xd8")
    if start < 0:
        return None
    end = buf.find(b"\xff\xd9", start + 2)
    if end < 0:
        return None
    return bytes(buf[start:end + 2])


class ArduCam:
    def __init__(self, spi_bus=0, spi_device=0, speed_hz=4_000_000,
                 cs_gpio=17, i2c_bus=1):
        # We drive chip select ourselves so it stays low for a whole frame read.
        try:
            self.cs = DigitalOutputDevice(cs_gpio, initial_value=True)
        except Exception as e:
            msg = str(e).lower()
            if "busy" in msg or "in use" in msg:
                raise CameraError(
                    "The camera is already in use. The turret is probably running in the background.\n"
                    "Stop it first with:  turret stop")
            if "permission" in msg or "denied" in msg:
                raise CameraError(NO_PERMISSION)
            raise

        self.spi = spidev.SpiDev()
        try:
            self.spi.open(spi_bus, spi_device)
        except FileNotFoundError:
            self.cs.close()
            raise CameraError(
                "/dev/spidev%d.%d not found. SPI is off. Run: sudo raspi-config nonint do_spi 0  then reboot."
                % (spi_bus, spi_device))
        except PermissionError:
            self.cs.close()
            raise CameraError(NO_PERMISSION)
        self.spi.max_speed_hz = speed_hz
        self.spi.mode = 0

        try:
            self.i2c = SMBus(i2c_bus)
        except FileNotFoundError:
            self.close()
            raise CameraError(
                "/dev/i2c-%d not found. I2C is off. Run: sudo raspi-config nonint do_i2c 0  then reboot." % i2c_bus)
        except PermissionError:
            self.close()
            raise CameraError(NO_PERMISSION)

        self.size = None
        self.photo_time = None

    # ---------- ArduChip over SPI ----------

    def write_reg(self, addr, value):
        self.cs.off()
        try:
            self.spi.xfer2([addr | 0x80, value & 0xFF])
        finally:
            self.cs.on()

    def read_reg(self, addr):
        self.cs.off()
        try:
            reply = self.spi.xfer2([addr & 0x7F, 0x00])
        finally:
            self.cs.on()
        return reply[1]

    def reset_chip(self):
        self.write_reg(RESET_REG, 0x80)
        time.sleep(0.1)
        self.write_reg(RESET_REG, 0x00)
        time.sleep(0.1)

    def check_spi(self):
        """Write 0x55 to the test register and read it back. Returns what came back."""
        self.write_reg(TEST_REG, 0x55)
        return self.read_reg(TEST_REG)

    def fifo_length(self):
        l1 = self.read_reg(FIFO_SIZE1)
        l2 = self.read_reg(FIFO_SIZE2)
        l3 = self.read_reg(FIFO_SIZE3) & 0x7F
        return ((l3 << 16) | (l2 << 8) | l1) & 0x7FFFFF

    # ---------- OV2640 sensor over I2C ----------

    def write_sensor(self, reg, value):
        self.i2c.write_byte_data(SENSOR_ADDR, reg, value)
        time.sleep(0.001)   # ArduCAM's library waits 1 ms after every write

    def read_sensor(self, reg):
        # The OV2640 wants a stop between setting the register and reading it.
        self.i2c.write_byte(SENSOR_ADDR, reg)
        return self.i2c.read_byte(SENSOR_ADDR)

    def write_sensor_table(self, table):
        for reg, value in table:
            self.write_sensor(reg, value)

    def sensor_id(self):
        """Returns (high, low). A working OV2640 gives (0x26, 0x41) or (0x26, 0x42)."""
        self.write_sensor(0xFF, 0x01)
        return self.read_sensor(0x0A), self.read_sensor(0x0B)

    # ---------- setup ----------

    def start(self, size=(320, 240)):
        if size not in SIZE_TABLES:
            raise CameraError("FRAME_SIZE must be one of %s" % list(SIZE_TABLES))

        self.reset_chip()

        got = self.check_spi()
        if got != 0x55:
            raise CameraError(
                "SPI check failed: wrote 0x55, read back 0x%02X. "
                "Check MOSI (pin 19), MISO (pin 21), SCK (pin 23), CS (pin 11)." % got)

        try:
            high, low = self.sensor_id()
        except OSError:
            raise CameraError(
                "Camera sensor did not answer on I2C. "
                "Check SDA (pin 3), SCL (pin 5), VCC (pin 1) and GND (pin 25).")
        if high != 0x26 or low not in (0x41, 0x42):
            raise CameraError(
                "Unexpected sensor ID 0x%02X 0x%02X, expected 0x26 0x41/0x42." % (high, low))

        # Same order as ArduCAM's InitCAM() for the OV2640 in JPEG mode.
        self.write_sensor(0xFF, 0x01)
        self.write_sensor(0x12, 0x80)      # soft reset the sensor
        time.sleep(0.1)
        self.write_sensor_table(regs.OV2640_JPEG_INIT)
        self.write_sensor_table(regs.OV2640_YUV422)
        self.write_sensor_table(regs.OV2640_JPEG)
        self.write_sensor(0xFF, 0x01)
        self.write_sensor(0x15, 0x00)
        self.write_sensor_table(SIZE_TABLES[size])

        self.write_reg(FIFO_REG, FIFO_CLEAR)
        self.write_reg(FRAMES_REG, 0x00)   # capture one frame per trigger
        self.size = size

        time.sleep(1.0)                    # let auto exposure settle

    # ---------- capture ----------

    def capture_jpeg(self, timeout=1.0):
        """Grab one frame. Returns JPEG bytes, or None if the frame was bad."""
        self.write_reg(FIFO_REG, FIFO_CLEAR)
        self.write_reg(FIFO_REG, FIFO_START)

        t0 = time.monotonic()
        while not (self.read_reg(TRIG_REG) & CAP_DONE):
            if time.monotonic() - t0 > timeout:
                raise CameraError("Camera never finished a frame. Check wiring and power.")
            time.sleep(0.001)
        # The picture was taken somewhere between these two moments.
        # The tracker uses this to know where the servos were pointing at the time.
        self.photo_time = (t0 + time.monotonic()) / 2

        length = self.fifo_length()
        if length == 0 or length >= MAX_FIFO_SIZE:
            self.write_reg(FIFO_REG, FIFO_CLEAR)
            return None

        data = bytearray()
        self.cs.off()
        try:
            self.spi.xfer2([BURST_FIFO_READ])
            remaining = length
            while remaining > 0:
                n = min(SPI_CHUNK, remaining)
                data += bytes(self.spi.readbytes(n))
                remaining -= n
        finally:
            self.cs.on()

        self.write_reg(FIFO_REG, FIFO_CLEAR)
        return extract_jpeg(data)

    def read(self):
        """Grab one frame as an OpenCV image, or None."""
        import cv2
        import numpy as np
        jpeg = self.capture_jpeg()
        if jpeg is None:
            return None
        return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)

    def close(self):
        for thing in ("spi", "i2c", "cs"):
            obj = getattr(self, thing, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
