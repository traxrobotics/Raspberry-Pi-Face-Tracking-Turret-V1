import cv2

import tracker


def test_detector_uses_a_real_model():
    d = tracker.FaceDetector()
    assert d.kind in ("YuNet", "SSD"), "models folder not found, got %s" % d.kind


def test_finds_the_face(face_image):
    d = tracker.FaceDetector()
    faces = d.detect(cv2.resize(face_image, (320, 240)))
    assert len(faces) >= 1
    x, y, w, h, score = max(faces, key=lambda f: f[4])
    assert score >= d.score
    assert 60 < x + w / 2 < 220 and 20 < y + h / 2 < 160   # the face sits upper left of center


def _feed(auto, detector, frame, rounds=12):
    turned_at = None
    for i in range(rounds):
        shown = auto.apply(frame)
        faces, turned = auto.check(shown, detector.detect(shown), detector)
        if turned and turned_at is None:
            turned_at = i
    return turned_at


def test_auto_orient_fixes_an_upside_down_camera(cfg, face_image):
    d = tracker.FaceDetector()
    auto = tracker.AutoOrient(cfg, d.kind)
    upside_down = cv2.rotate(cv2.resize(face_image, (320, 240)), cv2.ROTATE_180)
    assert _feed(auto, d, upside_down) is not None
    assert auto.extra == 180
    assert auto.confirmed


def test_auto_orient_leaves_an_upright_camera_alone(cfg, face_image):
    d = tracker.FaceDetector()
    auto = tracker.AutoOrient(cfg, d.kind)
    assert _feed(auto, d, cv2.resize(face_image, (320, 240))) is None
    assert auto.extra == 0
    assert auto.confirmed


def test_servos_hold_still_until_orientation_is_confirmed(cfg, face_image):
    d = tracker.FaceDetector()
    auto = tracker.AutoOrient(cfg, d.kind)
    frame = cv2.resize(face_image, (320, 240))
    faces, _ = auto.check(frame, d.detect(frame), d)
    assert faces == []          # first look: not sure yet, so nothing to steer toward
