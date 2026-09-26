import cv2
import hwstate
import pytest


def test_extract_jpeg_strips_junk_and_padding():
    from arducam import extract_jpeg
    jpeg = b"\xff\xd8 picture \xff\xd9"
    assert extract_jpeg(b"\x55" + jpeg + b"\x00" * 20) == jpeg


def test_extract_jpeg_rejects_broken_frames():
    from arducam import extract_jpeg
    assert extract_jpeg(b"\x00" * 50) is None
    assert extract_jpeg(b"\xff\xd8 cut off") is None


def test_spi_check_and_sensor_id(fast_camera):
    cam = fast_camera.ArduCam()
    try:
        assert cam.check_spi() == 0x55
        assert cam.sensor_id() == (0x26, 0x42)
    finally:
        cam.close()


def test_capture_returns_the_picture(fast_camera, face_image):
    cam = fast_camera.ArduCam()
    try:
        cam.start((320, 240))
        hwstate.FRAME_JPEG = cv2.imencode(".jpg", cv2.resize(face_image, (320, 240)))[1].tobytes()
        img = cam.read()
        assert img is not None and img.shape == (240, 320, 3)
        assert cam.photo_time is not None
    finally:
        cam.close()


def test_start_explains_a_dead_spi_bus(fast_camera):
    cam = fast_camera.ArduCam()
    hwstate.fail_spi = True
    try:
        with pytest.raises(fast_camera.CameraError, match="MISO"):
            cam.start((320, 240))
    finally:
        cam.close()


def test_start_rejects_unknown_frame_size(fast_camera):
    cam = fast_camera.ArduCam()
    try:
        with pytest.raises(fast_camera.CameraError, match="FRAME_SIZE"):
            cam.start((1024, 768))
    finally:
        cam.close()
