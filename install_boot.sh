#!/usr/bin/env bash
# Run ONCE:   bash install_boot.sh
# Then:       sudo reboot
#
# After that:
#   * the turret starts by itself every time the Pi boots
#   * the 'turret' command never asks for a password
#   * if something is off:  turret doctor
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
ME="$(id -un)"
SYSTEMCTL="$(command -v systemctl)"

if [ "$ME" = "root" ]; then
  echo "Run this as your normal user, not with sudo:  bash install_boot.sh"
  exit 1
fi
if [ ! -f "$DIR/tracker.py" ]; then
  echo "tracker.py is not next to this script. Run it from inside your turret folder."
  exit 1
fi

echo "This asks for your password once. After this, the turret command never will."
echo

echo "== 1. Removing the old start-on-boot attempt =="
systemctl --user disable --now turret.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/turret.service"
systemctl --user daemon-reload 2>/dev/null || true
sudo pkill -f "python3 .*[t]racker\.py" 2>/dev/null || true

echo "== 2. Letting $ME use the camera and servo pins without sudo (for tests and 'turret run') =="
sudo usermod -aG gpio,spi,i2c "$ME"
sudo tee /etc/udev/rules.d/99-turret-pwm.rules > /dev/null <<'EOF'
# Face tracking turret: let the gpio group control hardware PWM (GPIO12/13) without sudo
SUBSYSTEM=="pwm", ACTION=="add|change", RUN+="/bin/sh -c 'chgrp -R gpio /sys%p && chmod -R g+rwX /sys%p'"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=pwm --action=add || true

echo "== 3. Cleaning up files the old sudo runs left owned by root =="
sudo chown -R "$ME:$ME" "$DIR"
rm -f "$DIR"/.lgd-nfy* 2>/dev/null || true
chmod +x "$DIR/turret" "$DIR/doctor.sh"

echo "== 4. Making it start on boot =="
# A normal system service. It runs as root so it never trips over permissions
# at boot, and keeps retrying every few seconds until the camera and servos are ready.
sudo tee /etc/systemd/system/turret.service > /dev/null <<EOF
[Unit]
Description=Face tracking turret
After=multi-user.target
StartLimitIntervalSec=0

[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=/usr/bin/python3 -u $DIR/tracker.py
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=LG_WD=/run/turret
RuntimeDirectory=turret
StandardOutput=file:$DIR/turret.log
StandardError=inherit
Restart=always
RestartSec=3
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
EOF
sudo "$SYSTEMCTL" daemon-reload
sudo "$SYSTEMCTL" enable turret.service

echo "== 5. Letting the 'turret' command start and stop it with no password =="
TMP="$(mktemp)"
cat > "$TMP" <<EOF
# Face tracking turret: $ME may start/stop the turret service without a password. Nothing else.
$ME ALL=(root) NOPASSWD: $SYSTEMCTL start turret, $SYSTEMCTL stop turret, $SYSTEMCTL restart turret, $SYSTEMCTL enable --now turret, $SYSTEMCTL disable --now turret
EOF
if sudo visudo -cf "$TMP" > /dev/null; then
  sudo install -m 0440 -o root -g root "$TMP" /etc/sudoers.d/turret
else
  echo "Could not add the no-password rule. The turret still starts on boot."
fi
rm -f "$TMP"
sed -i "s|^SYSTEMCTL=.*|SYSTEMCTL=\"$SYSTEMCTL\"|" "$DIR/turret"

echo "== 6. Adding the 'turret' command =="
mkdir -p "$HOME/.local/bin"
ln -sf "$DIR/turret" "$HOME/.local/bin/turret"
sudo ln -sf "$DIR/turret" /usr/local/bin/turret     # works right away, no re-login needed

echo
echo "Done. Now run:  sudo reboot"
echo
echo "After the reboot the turret starts by itself."
echo "  turret status    is it running?"
echo "  turret doctor    checks everything if it is not"
