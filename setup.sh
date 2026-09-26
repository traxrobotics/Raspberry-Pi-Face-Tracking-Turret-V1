#!/usr/bin/env bash
# One time setup for the face tracking turret on a Raspberry Pi 5.
#   bash setup.sh
# Then reboot.
set -e

echo "== Installing packages =="
sudo apt update
sudo apt install -y python3-opencv opencv-data python3-numpy python3-spidev \
                    python3-gpiozero python3-lgpio i2c-tools
sudo apt install -y python3-smbus2 || sudo apt install -y python3-smbus

echo "== Turning on SPI and I2C =="
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0

echo "== Turning on hardware PWM for GPIO12 and GPIO13 =="
CFG=/boot/firmware/config.txt
LINE="dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4"
if grep -qxF "$LINE" "$CFG"; then
  echo "already in $CFG"
else
  printf '\n[all]\n%s\n' "$LINE" | sudo tee -a "$CFG" > /dev/null
  echo "added to $CFG"
fi

echo
echo "Setup done. Now run:  sudo reboot"
