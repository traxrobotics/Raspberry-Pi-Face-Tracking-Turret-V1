# Troubleshooting

Start with:

```bash
turret doctor
```

It checks the files, the boot service, SPI, I2C, the PWM overlay and your permissions,
and prints the fix for anything wrong plus the last lines of the log.

| What you see | Fix |
|---|---|
| SPI check reads 0x00 or 0xFF | MISO or VCC loose. Check pins 21 and 1. |
| Sensor did not answer on I2C | SDA pin 3, SCL pin 5, VCC pin 1, GND pin 25. |
| Only the fan PWM is present | The overlay line is missing. Check the end of `/boot/firmware/config.txt`, then reboot. |
| Servos do not move, no error | Run `pinctrl get 12,13`. Both should say PWM. If not, the overlay did not load. |
| Pi reboots when the servos move | Add the 1000 µF cap across a servo's red and brown wires, lower `SERVO_ACCEL`. |
| "Dropped to 4 MHz" in the log | Wires too long or loose for 8 MHz. Shorten them, or set `SPI_SPEED_HZ = 4_000_000`. |
| Frames fail a lot even at 4 MHz | Shorter camera wires, or `SPI_SPEED_HZ = 2_000_000`. |
| "No permission ... without sudo" | Run `bash install_boot.sh` once, then `sudo reboot`. |
| "The camera is already in use" | The background turret has it. `turret stop` first. |
| `turret: command not found` | Run `bash ~/turret/install_boot.sh` again. |
| Face detector says Haar | The `models` folder is missing. Keep it next to `tracker.py`. |
| Live view page will not load | Pi and phone on the same network? Port taken? Try `turret run` and read the output. |
| Does not start on boot | `turret doctor`. |

## Reporting a problem

Open an issue and paste the full output of `turret doctor`.
