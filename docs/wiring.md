# Wiring

Every connection from the ArduCAM B0067 and both SG90 servos into a Raspberry Pi 5 header.
14 of 40 pins used. No breakout board, no second supply.

> **Camera VCC goes to 3.3 V (pin 1). Never 5 V (pin 2).**
> The camera runs on either, but its output pins swing to whatever it is fed. The Pi's GPIO
> is not 5 V tolerant, so a camera on 5 V pushes 5 V back into the Pi on MISO and kills pins.
> Pin 1 and pin 2 sit right next to each other. Get this one right.

## Header map

Pin 1 is the inner row, at the end away from the USB ports. It has the only square solder pad.
Run `pinout` on the Pi to see it drawn.

```
                 3.3V  CAM VCC   1 ● ● 2   5V    PAN V+
            GPIO2      CAM SDA   3 ● ● 4   5V    TILT V+
            GPIO3      CAM SCL   5 ● ○ 6
                                 7 ○ ○ 8
                                 9 ○ ○ 10
           GPIO17      CAM CS   11 ● ○ 12
                                13 ○ ○ 14
                                15 ○ ○ 16
                                17 ○ ○ 18
           GPIO10     CAM MOSI  19 ● ○ 20
            GPIO9     CAM MISO  21 ● ○ 22
           GPIO11      CAM SCK  23 ● ○ 24
                       CAM GND  25 ● ○ 26
                                27 ○ ○ 28
                                29 ○ ● 30  GND   TILT GND
                                31 ○ ● 32  GPIO12  PAN SIGNAL
           GPIO13  TILT SIGNAL  33 ● ● 34  GND   PAN GND
                                35 ○ ○ 36
                                37 ○ ○ 38
                                39 ○ ○ 40
```

## Camera, 8 wires (female to female)

| Camera pin | Pi pin | Signal |
|---|---|---|
| VCC | 1 | 3.3 V power |
| GND | 25 | ground |
| SDA | 3 | GPIO2, I2C data |
| SCL | 5 | GPIO3, I2C clock |
| CS | 11 | GPIO17, chip select |
| MOSI | 19 | GPIO10, data out |
| MISO | 21 | GPIO9, data in |
| SCK | 23 | GPIO11, SPI clock |

CS is on GPIO17 instead of the hardware chip select on pin 24. That matches ArduCAM's own
Pi reference, and lets the driver hold CS low for a whole burst read, which the hardware line
would break between transfers.

Keep these eight wires under 15 cm and use stranded wire. They flex every time the head
moves, and solid core wire work hardens and snaps at the connector. Long wires are also the
main reason frames fail at 8 MHz SPI (the tracker drops to 4 MHz by itself if that happens).

## Servos, 6 wires (male to female)

| Servo | Wire | Pi pin | What it is |
|---|---|---|---|
| Pan (base) | orange | 32 | GPIO12 signal |
| | red | 2 | 5 V |
| | brown | 34 | ground |
| Tilt (top) | orange | 33 | GPIO13 signal |
| | red | 4 | 5 V |
| | brown | 30 | ground |

The SG90's three pin plug will not fit, because the pins it needs are not next to each
other on the header. Push male to female jumpers into the servo plug instead.

**Why GPIO12 and GPIO13:** only GPIO 12, 13, 18 and 19 have hardware PWM on a Pi 5.
Any other pin is software timed and the servos buzz and jitter.

**The capacitor:** put a 1000 µF, 10 V or higher electrolytic across one servo's red and brown
wires, at the servo end, stripe to brown. Fast starts pull current spikes that can dip the
Pi's 5 V rail and reboot it. The capacitor covers those spikes.

## Assembly order

1. Pi **unplugged**. Not asleep, not shut down with power still in.
2. Find pin 1 and prove it. Count from there, twice.
3. Camera signals and ground first, VCC into pin 1 last.
4. Servo signals to 32 and 33.
5. Servo grounds to 34 and 30, then 5 V to 2 and 4.
6. Capacitor across one servo's red and brown.
7. Check every wire against the map once more before power goes on.

## Planned: OLED eyes

An SSD1306 I2C OLED can join later without new signal pins. It shares the camera's I2C bus
(it answers at 0x3C, the camera at 0x30), so SDA and SCL need a split: a Y jumper, a small
breadboard, or solder the OLED wires onto the camera's SDA/SCL jumpers.

| OLED pin | Pi pin |
|---|---|
| VCC | 17 (3.3 V, pin 1 is already taken by the camera) |
| GND | 9 |
| SDA | 3 (shared with camera) |
| SCL | 5 (shared with camera) |

After wiring, `i2cdetect -y 1` should show both 30 and 3c.

## First power on

```bash
pinout               # confirm the Pi agrees with your pin numbering
ls /dev/spidev*      # expect /dev/spidev0.0
i2cdetect -y 1       # expect 30 in the grid (the OV2640 sensor)
python3 test_bus.py  # both lines should say OK
```

If the I2C grid is empty it is almost always VCC or GND, not the data lines.
Recheck pin 1 and pin 25 first.
