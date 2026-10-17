"""Tests for laser.py, using the fake gpiozero in tests/fakehw."""

from laser import Laser, make_laser


def test_make_laser_is_none_when_disabled(cfg):
    cfg.LASER_ENABLED = False
    assert make_laser(cfg) is None


def test_make_laser_builds_a_laser_when_enabled(cfg):
    cfg.LASER_ENABLED = True
    cfg.LASER_GPIO = 27
    laser = make_laser(cfg)
    assert laser is not None
    assert laser.pin.pin == 27
    laser.close()


def test_laser_on_off():
    laser = Laser(27)
    assert not laser.pin.is_active
    laser.on()
    assert laser.pin.is_active
    laser.off()
    assert not laser.pin.is_active
    laser.close()


def test_laser_close_turns_it_off_first():
    laser = Laser(27)
    laser.on()
    laser.close()
    assert not laser.pin.is_active


def test_laser_does_not_disturb_the_camera_chip_select():
    """A laser on its own GPIO must never look like the camera's CS pin to the fake SPI bus."""
    import hwstate

    hwstate.cs_low = True
    hwstate.burst = True
    laser = Laser(27)
    laser.on()
    laser.off()
    laser.close()
    assert hwstate.cs_low is True
    assert hwstate.burst is True
