"""Fake spidev that behaves like the ArduChip on an ArduCAM Mini 2MP Plus."""

import hwstate

FIFO_REG = 0x04
TRIG_REG = 0x41
BURST_FIFO_READ = 0x3C


class SpiDev:
    def open(self, bus, dev):
        self.max_speed_hz = 0
        self.mode = 0

    def close(self):
        pass

    def xfer2(self, data):
        assert hwstate.cs_low, "SPI transfer with CS high"
        addr = data[0]
        if len(data) == 1 and addr == BURST_FIFO_READ:
            hwstate.burst = True
            hwstate.burst_pos = 0
            return [0]
        if addr & 0x80:  # register write
            reg, val = addr & 0x7F, data[1]
            if reg == FIFO_REG:
                if val & 0x01:
                    hwstate.regs[TRIG_REG] = 0
                if val & 0x02:  # start capture: the "photo" is taken now
                    hwstate.fifo = b"\x55" + hwstate.FRAME_JPEG + b"\x00" * 37
                    hwstate.regs[TRIG_REG] = 0x08
            else:
                hwstate.regs[reg] = val
            return [0, 0]
        reg = addr & 0x7F  # register read
        if hwstate.fail_spi:
            return [0, 0xFF]
        n = len(hwstate.fifo)
        sizes = {0x42: n & 0xFF, 0x43: (n >> 8) & 0xFF, 0x44: (n >> 16) & 0x7F}
        return [0, sizes.get(reg, hwstate.regs.get(reg, 0))]

    def readbytes(self, n):
        assert hwstate.cs_low and hwstate.burst, "burst read without CS low"
        assert n <= 4096, "chunk too big for spidev: %d" % n
        out = hwstate.fifo[hwstate.burst_pos:hwstate.burst_pos + n]
        hwstate.burst_pos += n
        return list(out) + [0] * (n - len(out))
