"""
tests/test_motor.py – Unit tests for autofocus/motor.py (stub driver only)
"""

import pytest
from autofocus.motor import Direction, _StubDriver, create_driver


class TestStubDriver:
    def test_initial_position(self):
        d = _StubDriver()
        assert d.position == 0

    def test_step_forward(self):
        d = _StubDriver()
        d.step(5, Direction.FORWARD)
        assert d.position == 5

    def test_step_backward(self):
        d = _StubDriver()
        d.step(3, Direction.BACKWARD)
        assert d.position == -3

    def test_combined_steps(self):
        d = _StubDriver()
        d.step(10, Direction.FORWARD)
        d.step(4, Direction.BACKWARD)
        assert d.position == 6

    def test_position_setter(self):
        d = _StubDriver()
        d.position = 42
        assert d.position == 42

    def test_enable_disable_no_error(self):
        d = _StubDriver()
        d.enable()
        d.disable()

    def test_close_no_error(self):
        d = _StubDriver()
        d.close()


class TestCreateDriver:
    def test_stub_explicit(self):
        d = create_driver("stub")
        assert isinstance(d, _StubDriver)

    def test_unknown_falls_back_to_stub(self):
        # Non-Pi environment: gpio/i2c/spi will fail and return stub
        d = create_driver("gpio")
        assert isinstance(d, _StubDriver)
