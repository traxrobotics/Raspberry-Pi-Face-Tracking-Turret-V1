"""Shared state for the fake camera. Tests set FRAME_JPEG before capturing."""

cs_low = False
FRAME_JPEG = b""
regs = {0x00: 0, 0x41: 0}
fifo = b""
burst = False
burst_pos = 0
bank = None
sensor_ptr = None
fail_spi = False


def reset():
    global cs_low, FRAME_JPEG, fifo, burst, burst_pos, bank, sensor_ptr, fail_spi
    cs_low, FRAME_JPEG, fifo, burst, burst_pos = False, b"", b"", False, 0
    bank = sensor_ptr = None
    fail_spi = False
    regs.clear()
    regs.update({0x00: 0, 0x41: 0})
