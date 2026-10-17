# Wiring

Every connection from the ArduCAM B0067, both SG90 servos, and the laser pointer into a
Raspberry Pi 5 header. 15 of 40 pins used. No breakout board, no second supply.

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
       GPIO27  LASER SIGNAL   13 ● ○ 14  GND   LASER GND
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
7. Laser signal to 13, laser GND to 14, laser VCC spliced onto the 5 V rail at pin 2 or 4.
8. Check every wire against the map once more before power goes on.

## Laser pointer

A small 3 pin laser module (VCC, GND, S) has its own driver on the signal pin, so GPIO27
only needs to toggle on and off, the same way GPIO17 toggles the camera's chip select.

| Laser pin | Pi pin | Signal |
|---|---|---|
| S (signal) | 13 | GPIO27, on/off |
| VCC | 2 or 4 | 5 V, shared with a servo (the module draws far less current than an SG90) |
| GND | 14 | ground |

**The laser's aim is set by its mount, not by the code.** It sits in a bracket tilted down
off the camera's own axis, so the beam always lands below chin height no matter where the
turret is pointed. `laser.py` only ever turns it on while a face is being tracked and off
otherwise; it never aims it, and it must stay that way. Set `LASER_ENABLED = True` in
`config.py` once it is wired and the mount is in place.

## First power on

```bash
pinout               # confirm the Pi agrees with your pin numbering
ls /dev/spidev*      # expect /dev/spidev0.0
i2cdetect -y 1       # expect 30 in the grid (the OV2640 sensor)
python3 test_bus.py  # both lines should say OK
```

If the I2C grid is empty it is almost always VCC or GND, not the data lines.
Recheck pin 1 and pin 25 first.
