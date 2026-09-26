"""Fake smbus2 that answers like an OV2640 sensor at address 0x30."""

import hwstate


class SMBus:
    def __init__(self, bus):
        pass

    def close(self):
        pass

    def write_byte_data(self, addr, reg, val):
        assert addr == 0x30
        if reg == 0xFF:
            hwstate.bank = val

    def write_byte(self, addr, reg):
        hwstate.sensor_ptr = reg

    def read_byte(self, addr):
        if hwstate.bank == 0x01:
            return {0x0A: 0x26, 0x0B: 0x42}.get(hwstate.sensor_ptr, 0)
        return 0
