#!/usr/bin/env bash
# turret doctor: checks every piece and says in plain words what is wrong.
# Send the whole output if you need help.

DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
ME="$(id -un)"
SYSTEMCTL="$(command -v systemctl)"
BAD=0
ok()   { echo "  OK    $1"; }
bad()  { echo "  FAIL  $1"; [ -n "$2" ] && echo "        fix: $2"; BAD=$((BAD+1)); }
info() { echo "        $1"; }

echo "== Files =="
[ -f "$DIR/tracker.py" ] && ok "tracker.py in $DIR" || bad "tracker.py missing in $DIR" "clone the repo again"
[ -f "$DIR/config.py" ]  && ok "config.py"          || bad "config.py missing" "git checkout config.py  (or download it from the repo)"
if [ -f "$DIR/models/face_detection_yunet_2023mar.onnx" ] || [ -f "$DIR/models/res10_300x300_ssd_iter_140000.caffemodel" ]; then
  ok "face models"
else
  bad "models folder missing (face detection will be weak)" "download the models folder from the repo again"
fi

echo "== Boot service =="
if [ -f /etc/systemd/system/turret.service ]; then ok "service installed"; else bad "service not installed" "bash $DIR/install_boot.sh  then  sudo reboot"; fi
"$SYSTEMCTL" is-enabled --quiet turret 2>/dev/null && ok "starts on boot" || bad "not set to start on boot" "turret boot-on"
if "$SYSTEMCTL" is-active --quiet turret; then
  ok "running now"
else
  bad "not running now" "look at the log lines below for the reason"
fi
RESTARTS="$("$SYSTEMCTL" show turret -p NRestarts --value 2>/dev/null)"
[ -n "$RESTARTS" ] && [ "$RESTARTS" -gt 2 ] 2>/dev/null && bad "it has crashed and restarted $RESTARTS times" "the log below says why"
if systemctl --user is-active --quiet turret 2>/dev/null; then
  bad "the OLD background turret is also running" "systemctl --user disable --now turret"
fi
if sudo -n -l "$SYSTEMCTL" start turret >/dev/null 2>&1; then ok "turret command works with no password"; else bad "turret command would ask for a password" "bash $DIR/install_boot.sh"; fi

echo "== Hardware switched on =="
[ -e /dev/spidev0.0 ] && ok "SPI on" || bad "SPI off" "sudo raspi-config nonint do_spi 0  then reboot"
[ -e /dev/i2c-1 ]     && ok "I2C on" || bad "I2C off" "sudo raspi-config nonint do_i2c 0  then reboot"
if grep -qxF "dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4" /boot/firmware/config.txt 2>/dev/null; then
  ok "servo PWM line in config.txt"
else
  bad "servo PWM line missing from /boot/firmware/config.txt" "bash $DIR/setup.sh  then reboot"
fi
if command -v pinctrl >/dev/null; then
  P="$(pinctrl get 12,13 2>/dev/null)"
  if echo "$P" | grep -qi pwm; then ok "GPIO12/13 set to PWM"; else bad "GPIO12/13 are not PWM yet" "reboot after setup.sh"; info "$P"; fi
fi
for c in /sys/class/pwm/pwmchip*; do [ -e "$c" ] && info "$(basename "$c") -> $(readlink -f "$c" | sed 's|.*/\([^/]*\.pwm\)/.*|\1|')"; done

echo "== Running without sudo (tests and 'turret run') =="
for g in gpio spi i2c; do id -nG "$ME" | tr ' ' '\n' | grep -qx "$g" && ok "you are in group $g" || bad "you are not in group $g" "bash $DIR/install_boot.sh  then reboot"; done
[ -f /etc/udev/rules.d/99-turret-pwm.rules ] && ok "servo permission rule installed" || bad "servo permission rule missing" "bash $DIR/install_boot.sh"
W=0; for c in /sys/class/pwm/pwmchip*; do [ -w "$c/export" ] && W=1; done
[ "$W" = 1 ] && ok "you can control the servo PWM" || info "(servo PWM not writable by you. The boot service does not need this, only 'turret run' does)"

echo "== Last lines of turret.log =="
if [ -f "$DIR/turret.log" ]; then tail -n 12 "$DIR/turret.log" | sed 's/^/  | /'; else info "no log yet"; fi

echo
if [ "$BAD" = 0 ]; then echo "Everything looks fine."; else echo "$BAD problem(s) above. Fix the first one, then run: turret doctor"; fi
