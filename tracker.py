"""Track your face and move the servos to keep it in the middle of the picture.

    python3 tracker.py               # track and move
    python3 tracker.py --no-servos   # track only, servos stay still

After install_boot.sh it also runs by itself on boot. See the 'turret' command.

Watch it live in a browser at  http://<pi address>:8000
Press Ctrl+C to stop.
"""

import argparse
import math
import os
import signal
import socket
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

import config
from arducam import ArduCam, CameraError

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "models")


# ---------------- picture orientation ----------------

def rotation_setting(cfg):
    """ROTATE in config.py can be 0, 90, 180 or 270. Older configs used ROTATE_180."""
    r = getattr(cfg, "ROTATE", None)
    if r is None:
        r = 180 if getattr(cfg, "ROTATE_180", False) else 0
    r = int(r) % 360
    if r not in (0, 90, 180, 270):
        sys.exit("ROTATE in config.py must be 0, 90, 180 or 270")
    return r


def rotate(frame, degrees):
    if degrees == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if degrees == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if degrees == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame


def orient(frame, cfg):
    frame = rotate(frame, rotation_setting(cfg))
    if getattr(cfg, "MIRROR", False):
        frame = cv2.flip(frame, 1)
    return frame


# ---------------- face detector ----------------

def opencv_version():
    parts = cv2.__version__.split(".")
    return int(parts[0]), int(parts[1])


class FaceDetector:
    """Picks the best detector this Pi can run.

    YuNet    needs OpenCV 4.8 or newer. Small, fast, handles angles and dim light.
    SSD      works on any OpenCV 4. Very reliable, a bit slower.
    Haar     last resort if the model files are missing. Misses a lot.
    """

    def __init__(self, score=None):
        yunet = os.path.join(MODELS, "face_detection_yunet_2023mar.onnx")
        proto = os.path.join(MODELS, "deploy.prototxt")
        caffe = os.path.join(MODELS, "res10_300x300_ssd_iter_140000.caffemodel")
        self.kind = None
        self.input_size = None

        if opencv_version() >= (4, 8) and hasattr(cv2, "FaceDetectorYN") and os.path.exists(yunet):
            try:
                self.score = 0.6 if score is None else score
                self.yunet = cv2.FaceDetectorYN.create(yunet, "", (320, 240), self.score, 0.3, 50)
                self.kind = "YuNet"
            except cv2.error:
                self.kind = None

        if self.kind is None and os.path.exists(proto) and os.path.exists(caffe):
            self.score = 0.5 if score is None else score
            self.ssd = cv2.dnn.readNetFromCaffe(proto, caffe)
            self.kind = "SSD"

        if self.kind is None:
            self.score = 0
            self.haar = self._load_haar()
            self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            self.kind = "Haar (weak, the models folder is missing)"

    @staticmethod
    def _load_haar():
        paths = []
        if hasattr(cv2, "data"):
            paths.append(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
        paths += ["/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
                  "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml"]
        for p in paths:
            if os.path.exists(p):
                det = cv2.CascadeClassifier(p)
                if not det.empty():
                    return det
        sys.exit("No face model found. Put the models folder next to tracker.py.")

    def detect(self, frame):
        """Returns a list of (x, y, w, h, score) in pixels."""
        h, w = frame.shape[:2]

        if self.kind == "YuNet":
            if self.input_size != (w, h):
                self.yunet.setInputSize((w, h))
                self.input_size = (w, h)
            _, faces = self.yunet.detect(frame)
            if faces is None:
                return []
            return [(float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[-1])) for f in faces]

        if self.kind == "SSD":
            blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0))
            self.ssd.setInput(blob)
            out = self.ssd.forward()[0, 0]
            found = []
            for det in out:
                conf = float(det[2])
                if conf < self.score:
                    continue
                x1, y1 = max(0.0, det[3] * w), max(0.0, det[4] * h)
                x2, y2 = min(w - 1.0, det[5] * w), min(h - 1.0, det[6] * h)
                if x2 - x1 > 4 and y2 - y1 > 4:
                    found.append((x1, y1, x2 - x1, y2 - y1, conf))
            return found

        gray = self.clahe.apply(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        faces = self.haar.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(24, 24))
        return [(float(x), float(y), float(fw), float(fh), 1.0) for x, y, fw, fh in faces]


def pick_face(faces, previous):
    """Stick with the same person. If we were already following someone, take the
    face closest to where they were. Otherwise take the biggest, surest face."""
    if not faces:
        return None
    if previous is not None:
        px, py = previous
        return min(faces, key=lambda f: math.hypot(f[0] + f[2] / 2 - px, f[1] + f[3] / 2 - py))
    return max(faces, key=lambda f: f[2] * f[3] * f[4])


# ---------------- tracking math ----------------

MOTION_SIZE = (80, 60)


def small_gray(frame):
    """Tiny grey copy of a frame, for spotting motion cheaply."""
    return cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), MOTION_SIZE, interpolation=cv2.INTER_AREA)


def motion_hint(before, after, face_x, face_y, width, height):
    """Which way did things move between two frames, compared to where the face was?

    A head flicked out of the picture too fast to detect still leaves a smear of changed
    pixels on the side it went. Returns (dx, dy) in picture pixels from the last face
    center to the middle of the changed area, or None if hardly anything changed.
    """
    if before is None or after is None or face_x is None:
        return None
    changed = cv2.threshold(cv2.absdiff(before, after), 25, 255, cv2.THRESH_BINARY)[1]
    m = cv2.moments(changed, binaryImage=True)
    if m["m00"] < changed.size * 0.004:        # under 0.4% of the picture changed
        return None
    if m["m00"] > changed.size * 0.4:          # most of it changed: a light or the exposure, not a head
        return None
    sx, sy = width / MOTION_SIZE[0], height / MOTION_SIZE[1]
    return m["m10"] / m["m00"] * sx - face_x, m["m01"] / m["m00"] * sy - face_y


class Tracker:
    """Works out where the servos should aim so your face ends up in the middle.

    The lens sees FOV_DEG degrees across the picture, so a face 40 pixels off
    center is a known number of degrees off. The aim is: where the servos were
    when the photo was taken, plus that angle. One frame is enough to get most of
    the way there, then the ServoMover glides there smoothly.

    If the face is moving, it also aims a little ahead of it (LEAD in config.py),
    so the turret keeps up instead of always trailing behind.

    If the face vanishes near the edge of the picture, or while moving fast, it
    chases: turns hard toward where the face must have gone (CHASE in config.py).
    If that does not find it, it starts sweeping that way right away.

    With no face for RETURN_AFTER_S seconds it goes looking: a slow sweep side to
    side (SWEEP in config.py), starting toward the side the face left from.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.fov = float(getattr(cfg, "FOV_DEG", 60.0))
        self.correction = float(getattr(cfg, "CORRECTION", 0.9))
        self.lead = float(getattr(cfg, "LEAD", 1.0))
        self.pan = float(cfg.PAN_CENTER)      # current aim
        self.tilt = float(cfg.TILT_CENTER)
        self.face_x = None                    # last face center, for drawing
        self.face_y = None
        self.last_seen = time.monotonic()
        self._seen = deque()                  # recent (photo time, face pan angle, face tilt angle)
        self.vel_pan = 0.0                    # how fast the face is moving, degrees per second
        self.vel_tilt = 0.0

        # searching when nobody is in the picture
        self.sweep = bool(getattr(cfg, "SWEEP", True))
        self.sweep_speed = float(getattr(cfg, "SWEEP_SPEED", 30.0))
        self.sweep_min = max(cfg.PAN_MIN, float(getattr(cfg, "SWEEP_MIN", cfg.PAN_MIN)))
        self.sweep_max = min(cfg.PAN_MAX, float(getattr(cfg, "SWEEP_MAX", cfg.PAN_MAX)))
        self.sweep_tilt = float(getattr(cfg, "SWEEP_TILT", cfg.TILT_CENTER))
        self.sweeping = False
        self.sweep_dir = 1                    # +1 toward sweep_max, -1 toward sweep_min
        self.last_side = 0                    # which way the face was off center when last seen
        self.speed_limit = None               # slower top speed for the servos, None = full speed

        # chasing a face that just left the picture
        self.chase = bool(getattr(cfg, "CHASE", True))
        self.chase_deg = float(getattr(cfg, "CHASE_DEG", 20.0))
        self.chase_s = float(getattr(cfg, "CHASE_S", 0.7))
        self.chasing = False
        self.chased = False                   # a chase already ran for this loss
        self.lost = False                     # the face is currently missing
        self.last_ang = None                  # where the face really was when last seen (pan, tilt)
        self.last_photo = None                # photo time of that sighting
        self.jump = (0.0, 0.0)                # speed between the last two sightings, degrees per second
        self.last_servo_speed = 0.0           # how fast the servos moved at the last sighting
        self.streak_start = None              # when the current unbroken run of sightings began
        self.last_chase = -1e9                # when the last chase started
        self.last_edge = (0, 0)               # was it near the left/right, top/bottom edge

    FAST_SERVO = 150.0        # degrees per second. While the servos move faster than this,
                              # where they pointed at photo time is too uncertain to judge speed
    SPEED_WINDOW_S = 0.4      # judge the face's speed over this much recent time
    SPEED_MIN_SPAN_S = 0.15   # need at least this much to trust it

    def _track_speed(self, when, ang_pan, ang_tilt):
        """Work out how fast the face is moving across the room, in degrees per second.

        Uses a straight line fit over the last 0.4 s instead of just two frames, so
        a box that wobbles by a pixel or two does not look like movement.
        """
        seen = self._seen
        if seen and when - seen[-1][0] > 0.5:
            seen.clear()                   # long gap, old samples mean nothing now
        seen.append((when, ang_pan, ang_tilt))
        while seen and when - seen[0][0] > self.SPEED_WINDOW_S:
            seen.popleft()
        if len(seen) < 3 or seen[-1][0] - seen[0][0] < self.SPEED_MIN_SPAN_S:
            self.vel_pan = self.vel_tilt = 0.0
            return
        t_avg = sum(s[0] for s in seen) / len(seen)
        p_avg = sum(s[1] for s in seen) / len(seen)
        q_avg = sum(s[2] for s in seen) / len(seen)
        tt = sum((s[0] - t_avg) ** 2 for s in seen)
        self.vel_pan = sum((s[0] - t_avg) * (s[1] - p_avg) for s in seen) / tt
        self.vel_tilt = sum((s[0] - t_avg) * (s[2] - q_avg) for s in seen) / tt

    def _lead(self, vel, ahead):
        """How far ahead of the face to aim. Ignores tiny speeds, those are just jitter."""
        if abs(vel) < self.MIN_LEAD_SPEED:
            return 0.0
        return max(-self.MAX_LEAD_DEG, min(self.MAX_LEAD_DEG, vel * ahead))

    MIN_LEAD_SPEED = 8.0      # degrees per second. Slower than this is treated as sitting still
    MAX_LEAD_DEG = 12.0       # never aim more than this far ahead of the face
    SERVO_CATCH_UP_S = 0.08   # extra time the servos need to get where they are sent

    EDGE_FRAC = 0.45          # face center this far from the middle toward an edge = "near the edge"
    CHASE_SPEED = 25.0        # degrees per second. A face moving faster than this and then gone = chase

    def _chase_dir(self, vel, edge):
        if abs(vel) >= self.CHASE_SPEED:
            return 1 if vel > 0 else -1
        return edge

    @staticmethod
    def _faster(a, b):
        return a if abs(a) >= abs(b) else b

    def _motion_dirs(self, motion, width, height):
        """Direction from the motion hint. Left/right only: your shoulders and body sit below
        your face, so the changed area always leans downward and up/down cannot be trusted."""
        if motion is None:
            return 0, 0
        dx = motion[0] / width                # as a share of the picture width
        if abs(dx) > 0.04:
            return (self.cfg.PAN_DIR if dx > 0 else -self.cfg.PAN_DIR), 0
        return 0, 0

    STEADY_S = 0.3            # the face must have been tracked this long for its last sighting to be trusted

    def _start_chase(self, now, motion=None, width=320, height=240):
        """The face just vanished. If it left over an edge or was moving fast, go after it.

        Speed comes from the smooth 0.4 s estimate or, for a sudden flick that only
        shows up in the very last frame, from the jump between the last two sightings.
        """
        # Only trust the last sighting if the turret was fairly still and had been
        # following the face for a moment. Otherwise a blurry glimpse mid swing could send
        # it the wrong way, and chases would bounce back and forth.
        if self.last_servo_speed >= self.FAST_SERVO:
            return
        if self.streak_start is None or self.last_seen - self.streak_start < self.STEADY_S:
            return
        if now - self.last_chase < 1.5:
            return
        vp = self._faster(self.vel_pan, self.jump[0])
        vt = self._faster(self.vel_tilt, self.jump[1])
        dp = self._chase_dir(vp, self.last_edge[0])
        dt = self._chase_dir(vt, self.last_edge[1])
        if dp == 0 and dt == 0:               # vanished with no other clue: follow the smear
            dp, dt = self._motion_dirs(motion, width, height)
        if not self.chase or self.last_ang is None or (dp == 0 and dt == 0):
            return
        # Aim past where it was last seen, further if it was moving fast.
        extra_p = max(self.chase_deg, min(40.0, abs(vp) * 0.2))
        extra_t = max(self.chase_deg * 0.6, min(25.0, abs(vt) * 0.2))
        self.pan = self.last_ang[0] + dp * extra_p if dp else self.pan
        self.tilt = self.last_ang[1] + dt * extra_t if dt else self.tilt
        if dp:
            self.last_side = dp               # if the chase misses, sweep this way
        self.chasing = self.chased = True
        self.last_chase = now
        self.speed_limit = None

    def _sweep_step(self, pan_now):
        """Nobody in the picture: pan slowly from side to side until a face shows up."""
        if not self.sweeping:
            self.sweeping = True
            self.sweep_dir = self.last_side or 1      # first look where you walked off to
        end = self.sweep_max if self.sweep_dir > 0 else self.sweep_min
        if (pan_now - end) * self.sweep_dir >= -2.0:  # reached this end, turn around
            self.sweep_dir = -self.sweep_dir
            end = self.sweep_max if self.sweep_dir > 0 else self.sweep_min
        self.pan, self.tilt = end, self.sweep_tilt
        self.speed_limit = self.sweep_speed

    def update(self, face, width, height, pan_at_photo, tilt_at_photo, now=None, photo_time=None,
               servo_speed=0.0, motion=None):
        cfg = self.cfg
        now = time.monotonic() if now is None else now
        photo_time = now if photo_time is None else photo_time

        if face is not None:
            x, y, w, h = face[:4]
            fx, fy = x + w / 2.0, y + h / 2.0
            self.face_x, self.face_y = fx, fy
            deg_per_px = self.fov / max(width, height)   # the 60 degrees span the long side
            err_x = fx - width / 2.0      # + means face is right of center
            err_y = fy - height / 2.0     # + means face is below center

            off_pan = cfg.PAN_DIR * err_x * deg_per_px       # degrees from where the camera pointed
            off_tilt = cfg.TILT_DIR * err_y * deg_per_px

            # Where the face really was when the photo was taken. Used to judge its speed.
            if servo_speed < self.FAST_SERVO:
                self._track_speed(photo_time, pan_at_photo + off_pan, tilt_at_photo + off_tilt)
            else:
                self._seen.clear()        # mid snap: the turret is already moving fast, no lead needed
                self.vel_pan = self.vel_tilt = 0.0

            # Where to aim: at the face (CORRECTION < 1 stops a little short, so it never
            # swings past), plus a little ahead if the face is moving, because it has
            # already moved on since the photo was taken.
            if abs(off_pan) > 1.0:
                self.last_side = 1 if off_pan > 0 else -1
            self.sweeping = False
            self.speed_limit = None
            if self.lost or self.streak_start is None:
                self.streak_start = now
            self.chasing = self.chased = self.lost = False
            ang = (pan_at_photo + off_pan, tilt_at_photo + off_tilt)
            steady = servo_speed < self.FAST_SERVO and self.last_servo_speed < self.FAST_SERVO
            if steady and self.last_ang is not None and self.last_photo is not None \
                    and 0.02 < photo_time - self.last_photo < 0.3:
                gap = photo_time - self.last_photo
                self.jump = ((ang[0] - self.last_ang[0]) / gap, (ang[1] - self.last_ang[1]) / gap)
            else:
                self.jump = (0.0, 0.0)
            self.last_ang, self.last_photo = ang, photo_time
            self.last_servo_speed = servo_speed
            edge_x = err_x / (width / 2.0)            # -1 left edge .. +1 right edge
            edge_y = err_y / (height / 2.0)
            self.last_edge = (
                (cfg.PAN_DIR if edge_x > 0 else -cfg.PAN_DIR) if abs(edge_x) > self.EDGE_FRAC else 0,
                (cfg.TILT_DIR if edge_y > 0 else -cfg.TILT_DIR) if abs(edge_y) > self.EDGE_FRAC else 0,
            )

            ang_pan = pan_at_photo + off_pan * self.correction
            ang_tilt = tilt_at_photo + off_tilt * self.correction
            ahead = self.lead * (min(0.3, max(0.0, now - photo_time)) + self.SERVO_CATCH_UP_S)

            # The deadzone stops twitching while you sit still. While you move it is
            # ignored, otherwise the turret would stop every time it caught up.
            if abs(err_x) > cfg.DEADZONE_X or abs(self.vel_pan) >= self.MIN_LEAD_SPEED:
                self.pan = ang_pan + self._lead(self.vel_pan, ahead)
            if abs(err_y) > cfg.DEADZONE_Y or abs(self.vel_tilt) >= self.MIN_LEAD_SPEED:
                self.tilt = ang_tilt + self._lead(self.vel_tilt, ahead)
            self.last_seen = now

        else:
            if not self.lost:
                self.lost = True
                self._start_chase(now, motion, width, height)   # uses the speed from before it vanished
            if self.chasing and now - self.last_seen > self.chase_s:
                self.chasing = False          # chase found nothing, sweep from here
            if now - self.last_seen > 0.5:
                # Gone for more than a moment. Forget how fast it was moving.
                # (A single missed frame keeps the speed, so the lead does not stutter.)
                self._seen.clear()
                self.vel_pan = self.vel_tilt = 0.0
            # After a chase that found nothing, sweep right away. Without sweeping, hold the
            # chase spot for the usual wait before going back to center.
            chased_lately = self.chased or now - self.last_chase < 3.0
            give_up = self.chase_s if (chased_lately and self.sweep) else cfg.RETURN_AFTER_S
            if not self.chasing and now - self.last_seen > give_up:
                self.face_x = self.face_y = None
                if self.sweep:
                    self._sweep_step(pan_at_photo)
                else:
                    # Lost you for a while. Aim back at the middle (the mover glides there).
                    self.pan, self.tilt = float(cfg.PAN_CENTER), float(cfg.TILT_CENTER)

        self.pan = max(cfg.PAN_MIN, min(cfg.PAN_MAX, self.pan))
        self.tilt = max(cfg.TILT_MIN, min(cfg.TILT_MAX, self.tilt))
        return self.pan, self.tilt


class AutoOrient:
    """Notices a sideways or upside down camera and turns the picture itself.

    This matters a lot. An upside down face is either missed, or found and
    tracked backwards, so the turret runs away from you.

    How it tells: a face detector is always surest about an upright face.
    So it scores the picture as is, and turned 90, 180 and 270 degrees, and
    keeps whichever way it is most confident about. The servos stay still
    until that check passes, so they never chase an upside down face.
    Turn this off with AUTO_ROTATE = False in config.py.
    """

    VOTES_NEEDED = 3
    MARGIN = 0.05          # a turned picture must beat the current one by this much

    def __init__(self, cfg, detector_kind="YuNet"):
        self.base = rotation_setting(cfg)
        self.enabled = getattr(cfg, "AUTO_ROTATE", True)
        # Once running fine, recheck every this many face frames. SSD is slower, check less.
        # Each check costs 3 extra face searches, so once the picture keeps passing,
        # check less and less often (up to every 320 face frames).
        self.first_every = 20 if detector_kind == "YuNet" else 60
        self.check_every = self.first_every
        self.extra = 0
        self.votes = {90: 0, 180: 0, 270: 0}
        self.misses = 0
        self.face_frames = 0
        self.confirmed = not self.enabled
        self.agree = 0
        self.message = ""

    def apply(self, frame):
        return rotate(frame, self.extra)

    def _best_turn(self, frame, detector, current_score):
        best, best_score = 0, 0.0
        for turn in (90, 180, 270):
            faces = detector.detect(rotate(frame, turn))
            if faces:
                s = max(f[4] for f in faces)
                if s > best_score:
                    best, best_score = turn, s
        if best and best_score > current_score + self.MARGIN:
            return best
        return 0

    def _vote(self, turn):
        self.votes[turn] += 1
        if self.votes[turn] < self.VOTES_NEEDED:
            return False
        self.extra = (self.extra + turn) % 360
        self.votes = {90: 0, 180: 0, 270: 0}
        self.confirmed, self.agree = False, 0      # double check the new way up
        self.check_every = self.first_every
        total = (self.base + self.extra) % 360
        self.message = "auto-turned picture. Put ROTATE = %d in config.py" % total
        print()
        print("*** The camera picture was turned. Fixed it automatically. ***")
        print("*** To skip this next time, put  ROTATE = %d  in config.py ***" % total)
        print()
        return True

    def check(self, frame, faces, detector):
        """Returns (faces safe to steer toward, True if the picture just got turned)."""
        if not self.enabled:
            return faces, False

        if faces:
            self.misses = 0
            self.face_frames += 1
            if not self.confirmed or self.face_frames % self.check_every == 0:
                turn = self._best_turn(frame, detector, max(f[4] for f in faces))
                if turn == 0:
                    self.votes = {90: 0, 180: 0, 270: 0}
                    self.agree += 1
                    if self.confirmed:
                        self.check_every = min(320, self.check_every * 2)
                    if self.agree >= 2:
                        self.confirmed = True
                else:
                    return [], self._vote(turn)    # might be backwards, do not steer
            if not self.confirmed:
                return [], False                   # still checking, hold still
            return faces, False

        self.misses += 1
        if self.misses % 10 == 0:
            turn = self._best_turn(frame, detector, 0.0)
            if turn:
                return [], self._vote(turn)
        return [], False


# ---------------- camera in its own thread ----------------

class FrameGrabber:
    """Reads the camera in the background.

    Taking a photo and pulling it over SPI is the slowest part of the loop. Doing
    it in its own thread means the next photo is already on its way while the
    last one is searched for a face, so there are more frames per second and each
    one is fresher.

    If frames keep failing at a fast SPI speed (long or loose wires), it drops to
    a slower speed by itself and says so.
    """

    SAFE_SPI_HZ = 4_000_000

    def __init__(self, cam, cfg):
        self.cam = cam
        self.cfg = cfg
        self.cond = threading.Condition()
        self.frame = None
        self.photo_time = None
        self.seq = 0
        self.error = None
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _restart(self):
        spi = self.cam.spi
        if spi.max_speed_hz > self.SAFE_SPI_HZ:
            spi.max_speed_hz = self.SAFE_SPI_HZ
            print("Frames keep failing at this SPI speed. Dropped to 4 MHz.")
            print("To skip this next time, put  SPI_SPEED_HZ = 4_000_000  in config.py")
        print("Restarting camera...")
        try:
            self.cam.start(self.cfg.FRAME_SIZE)
        except CameraError as e:
            print("Camera restart failed:", e)
            time.sleep(1.0)

    def _run(self):
        bad = 0
        try:
            while self.running:
                try:
                    frame = self.cam.read()
                except CameraError as e:
                    print("Camera hiccup:", e)
                    frame = None
                if frame is None:
                    bad += 1
                    if bad >= 5:
                        self._restart()
                        bad = 0
                    continue
                bad = 0
                with self.cond:
                    self.frame, self.photo_time = frame, self.cam.photo_time
                    self.seq += 1
                    self.cond.notify_all()
        except BaseException as e:          # hand anything unexpected to the main loop
            with self.cond:
                self.error = e
                self.cond.notify_all()

    def next(self, last_seq, timeout=2.0):
        """Wait for a photo newer than last_seq. Returns (frame, photo_time, seq) or None."""
        with self.cond:
            self.cond.wait_for(lambda: self.seq != last_seq or self.error is not None, timeout)
            if self.error is not None:
                raise self.error
            if self.seq == last_seq:
                return None
            return self.frame, self.photo_time, self.seq

    def stop(self):
        self.running = False
        self.thread.join(timeout=2.0)


# ---------------- live browser view ----------------

class LiveView:
    def __init__(self, port):
        self.jpeg = None
        self.viewers = 0          # browsers watching. No one watching = skip drawing and JPEG work
        self.cond = threading.Condition()
        view = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == "/":
                    page = (b"<html><head><title>Turret</title></head>"
                            b"<body style='margin:0;background:#111;display:flex;"
                            b"justify-content:center;align-items:center;height:100vh'>"
                            b"<img src='/stream' style='width:100%;height:100%;object-fit:contain'>"
                            b"</body></html>")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(page)))
                    self.end_headers()
                    self.wfile.write(page)
                    return
                if self.path != "/stream":
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()
                with view.cond:
                    view.viewers += 1
                try:
                    while True:
                        with view.cond:
                            view.cond.wait(timeout=2)
                            data = view.jpeg
                        if data is None:
                            continue
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                        self.wfile.write(b"Content-Length: %d\r\n\r\n" % len(data))
                        self.wfile.write(data)
                        self.wfile.write(b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    with view.cond:
                        view.viewers -= 1

        self.server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def publish(self, frame):
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with self.cond:
                self.jpeg = buf.tobytes()
                self.cond.notify_all()

    def close(self):
        self.server.shutdown()


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))   # nothing is sent, this just picks the right interface
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "localhost"


def draw_overlay(frame, face, holding, tracker, cfg, status, hint):
    h, w = frame.shape[:2]
    cx, cy = w // 2, h // 2
    dim = (90, 90, 90)
    cv2.rectangle(frame, (cx - cfg.DEADZONE_X, cy - cfg.DEADZONE_Y),
                  (cx + cfg.DEADZONE_X, cy + cfg.DEADZONE_Y), dim, 1)
    cv2.line(frame, (cx - 6, cy), (cx + 6, cy), dim, 1)
    cv2.line(frame, (cx, cy - 6), (cx, cy + 6), dim, 1)
    if face is not None:
        x, y, fw, fh = [int(v) for v in face[:4]]
        color = (0, 180, 255) if holding else (60, 200, 90)   # orange = holding last spot
        cv2.rectangle(frame, (x, y), (x + fw, y + fh), color, 2)
    if tracker.face_x is not None:
        cv2.circle(frame, (int(tracker.face_x), int(tracker.face_y)), 3, (40, 120, 230), -1)
    cv2.putText(frame, status, (6, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (230, 230, 230), 1, cv2.LINE_AA)
    if hint:
        cv2.putText(frame, hint, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (60, 200, 255), 1, cv2.LINE_AA)


# ---------------- main loop ----------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-servos", action="store_true", help="track only, do not move")
    parser.add_argument("--no-view", action="store_true", help="skip the browser view")
    args = parser.parse_args()
    cfg = config

    # When the boot service is stopped, finish cleanly (center and relax the servos).
    def on_stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, on_stop)

    detector = FaceDetector(getattr(cfg, "FACE_SCORE", None))
    print("Face detector: %s  (OpenCV %s)" % (detector.kind, cv2.__version__))

    try:
        cam = ArduCam(cfg.SPI_BUS, cfg.SPI_DEVICE, cfg.SPI_SPEED_HZ, cfg.CS_GPIO, cfg.I2C_BUS)
        print("Starting camera...")
        cam.start(cfg.FRAME_SIZE)
    except CameraError as e:
        sys.exit("Camera: %s" % e)

    pan = tilt = mover = None
    if not args.no_servos:
        from servo import ServoError, ServoMover, make_servos
        try:
            chip, pan, tilt = make_servos(cfg)
        except ServoError as e:
            cam.close()
            sys.exit("Servos: %s" % e)
        print("Servos on", chip)
        pan.write(cfg.PAN_CENTER)
        time.sleep(0.5)                  # one at a time, so the 5V rail does not dip
        tilt.write(cfg.TILT_CENTER)
        time.sleep(0.5)
        mover = ServoMover(pan, tilt, cfg.PAN_CENTER, cfg.TILT_CENTER,
                           speed=getattr(cfg, "SERVO_SPEED", 550.0),
                           accel=getattr(cfg, "SERVO_ACCEL", 4500.0))

    view = None
    if not args.no_view:
        try:
            view = LiveView(cfg.STREAM_PORT)
            print("Live view: http://%s:%d" % (local_ip(), cfg.STREAM_PORT))
        except OSError:
            print("Live view off: port %d is already taken (another turret running?)" % cfg.STREAM_PORT)

    tracker = Tracker(cfg)
    auto = AutoOrient(cfg, detector.kind)
    hold_s = getattr(cfg, "HOLD_FACE_S", 0.5)
    last_face, last_face_time = None, 0.0

    fps, frames, found_count = 0.0, 0, 0
    last_print = time.monotonic()
    status = "starting"
    grabber = FrameGrabber(cam, cfg)
    seq = 0
    small_before = None
    print("Tracking. Ctrl+C to stop.")

    try:
        while True:
            got = grabber.next(seq)
            if got is None:
                continue
            frame, photo_time, seq = got
            servo_speed = 0.0
            if mover is not None:
                pan_at_photo, tilt_at_photo = mover.position_at(photo_time)
                p0, t0 = mover.position_at(photo_time - 0.04)
                servo_speed = math.hypot(pan_at_photo - p0, tilt_at_photo - t0) / 0.04
            else:
                pan_at_photo, tilt_at_photo = cfg.PAN_CENTER, cfg.TILT_CENTER

            frame = auto.apply(orient(frame, cfg))
            h, w = frame.shape[:2]
            now = time.monotonic()

            faces, turned = auto.check(frame, detector.detect(frame), detector)
            if turned:
                # Old positions were in the old picture. Start fresh.
                tracker.face_x = tracker.face_y = None
                last_face = None

            previous = None
            if last_face is not None and now - last_face_time < 1.0:
                previous = (last_face[0] + last_face[2] / 2, last_face[1] + last_face[3] / 2)
            face = pick_face(faces, previous)

            holding = False
            if face is not None:
                last_face, last_face_time = face, now
                found_count += 1
            elif last_face is not None and now - last_face_time < hold_s:
                holding = True       # missed one frame, keep the box, do not move

            # The moment the face vanishes, look at what moved (only while the camera is
            # fairly still, otherwise the whole picture changes).
            small_now = small_gray(frame)
            motion = None
            if face is None and not tracker.lost and servo_speed < 60:
                motion = motion_hint(small_before, small_now, tracker.face_x, tracker.face_y, w, h)
            small_before = small_now

            p, t = tracker.update(face, w, h, pan_at_photo, tilt_at_photo, now, photo_time, servo_speed, motion)
            if mover is not None:
                mover.set_target(p, t, tracker.speed_limit)
                p, t = mover.position()

            frames += 1
            if now - last_print >= 2.0:
                fps = frames / (now - last_print)
                rate = 100.0 * found_count / max(1, frames)
                status = "%s  face %3.0f%%  pan %d  tilt %d  %.0f fps" % (detector.kind.split()[0], rate, p, t, fps)
                mode = "   searching" if tracker.sweeping else ("   chasing" if tracker.chasing else "")
                print("%4.1f fps   face found %3.0f%% of frames   pan %5.1f   tilt %5.1f%s"
                      % (fps, rate, p, t, mode))
                frames, found_count = 0, 0
                last_print = now

            if view is not None and view.viewers > 0:
                shown = face if face is not None else (last_face if holding else None)
                hint = auto.message or ("searching..." if tracker.sweeping else
                                        "chasing..." if tracker.chasing else "")
                draw_overlay(frame, shown, holding, tracker, cfg, status, hint)
                view.publish(frame)

    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        grabber.stop()
        if mover is not None:
            mover.settle(cfg.PAN_CENTER, cfg.TILT_CENTER)
            mover.stop()
            pan.release()
            tilt.release()
        if view is not None:
            view.close()
        cam.close()


if __name__ == "__main__":
    main()
