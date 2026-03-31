"""
motor.py – Motor driver communication interface (GPIO / I2C / SPI).

Supports three back-ends selected at runtime:
  * gpio   – step/direction via RPi.GPIO
  * i2c    – I²C motor driver (e.g. DRV8830)
  * spi    – SPI motor driver (e.g. L6470)

If the requested hardware library is unavailable (non-Pi environment)
the driver falls back to a software stub that logs movements instead
of actuating hardware.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Literal, Optional

logger = logging.getLogger(__name__)

DriverType = Literal["gpio", "i2c", "spi", "stub"]


# ---------------------------------------------------------------------------
# Step direction
# ---------------------------------------------------------------------------

class Direction(Enum):
    FORWARD = 1
    BACKWARD = -1


# ---------------------------------------------------------------------------
# Stub driver (always available)
# ---------------------------------------------------------------------------

class _StubDriver:
    """Software-only driver: logs moves, carries no hardware dependency."""

    def __init__(self) -> None:
        self._position: int = 0

    def step(self, count: int, direction: Direction, delay_us: int = 500) -> None:
        self._position += direction.value * count
        logger.debug("Stub motor: step %+d  →  pos=%d", direction.value * count, self._position)

    def enable(self) -> None:
        logger.debug("Stub motor: enabled")

    def disable(self) -> None:
        logger.debug("Stub motor: disabled")

    def close(self) -> None:
        pass

    @property
    def position(self) -> int:
        return self._position

    @position.setter
    def position(self, value: int) -> None:
        self._position = value


# ---------------------------------------------------------------------------
# GPIO driver
# ---------------------------------------------------------------------------

class _GPIODriver:
    """
    Bipolar stepper via two GPIO pins: STEP and DIR.

    Pin assignments are configurable; defaults target common breakout boards.
    """

    def __init__(self, step_pin: int = 23, dir_pin: int = 24) -> None:
        try:
            import RPi.GPIO as GPIO  # noqa: PLC0415
            self._GPIO = GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(step_pin, GPIO.OUT)
            GPIO.setup(dir_pin, GPIO.OUT)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"GPIO init failed: {exc}") from exc
        self._step_pin = step_pin
        self._dir_pin = dir_pin
        self._position = 0

    def step(self, count: int, direction: Direction, delay_us: int = 500) -> None:
        GPIO = self._GPIO
        GPIO.output(self._dir_pin, GPIO.HIGH if direction == Direction.FORWARD else GPIO.LOW)
        delay_s = delay_us / 1_000_000
        for _ in range(count):
            GPIO.output(self._step_pin, GPIO.HIGH)
            time.sleep(delay_s)
            GPIO.output(self._step_pin, GPIO.LOW)
            time.sleep(delay_s)
        self._position += direction.value * count

    def enable(self) -> None:
        pass   # No enable pin in this minimal wiring

    def disable(self) -> None:
        pass

    def close(self) -> None:
        self._GPIO.cleanup([self._step_pin, self._dir_pin])

    @property
    def position(self) -> int:
        return self._position

    @position.setter
    def position(self, value: int) -> None:
        self._position = value


# ---------------------------------------------------------------------------
# I²C driver (DRV8830-style, single-byte speed+direction register)
# ---------------------------------------------------------------------------

class _I2CDriver:
    """Minimal I²C stepper / DC motor driver."""

    _REG_CONTROL = 0x00

    def __init__(self, bus: int = 1, address: int = 0x60) -> None:
        try:
            import smbus2  # noqa: PLC0415
            self._bus = smbus2.SMBus(bus)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"I2C init failed: {exc}") from exc
        self._address = address
        self._position = 0

    def step(self, count: int, direction: Direction, delay_us: int = 500) -> None:
        vset = 0b111111    # maximum voltage setting
        in1 = 0b01 if direction == Direction.FORWARD else 0b10
        byte = (vset << 2) | in1
        delay_s = delay_us / 1_000_000
        try:
            for _ in range(count):
                self._bus.write_byte_data(self._address, self._REG_CONTROL, byte)
                time.sleep(delay_s)
                # coast
                self._bus.write_byte_data(self._address, self._REG_CONTROL, 0x00)
                time.sleep(delay_s)
        except Exception as exc:  # noqa: BLE001
            logger.error("I2C step error: %s", exc)
        self._position += direction.value * count

    def enable(self) -> None:
        pass

    def disable(self) -> None:
        try:
            self._bus.write_byte_data(self._address, self._REG_CONTROL, 0x00)
        except Exception:  # noqa: BLE001
            pass

    def close(self) -> None:
        self.disable()
        self._bus.close()

    @property
    def position(self) -> int:
        return self._position

    @position.setter
    def position(self, value: int) -> None:
        self._position = value


# ---------------------------------------------------------------------------
# SPI driver (L6470 dSPIN-style)
# ---------------------------------------------------------------------------

class _SPIDriver:
    """Minimal SPI stepper driver (L6470 command subset)."""

    _CMD_RUN   = 0x50
    _CMD_STOP  = 0xB0

    def __init__(self, bus: int = 0, device: int = 0) -> None:
        try:
            import spidev  # noqa: PLC0415
            self._spi = spidev.SpiDev()
            self._spi.open(bus, device)
            self._spi.max_speed_hz = 1_000_000
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"SPI init failed: {exc}") from exc
        self._position = 0

    def step(self, count: int, direction: Direction, delay_us: int = 500) -> None:
        speed = min(count * 10, 0x000FFFFF)
        dir_bit = 0x01 if direction == Direction.FORWARD else 0x00
        cmd = self._CMD_RUN | dir_bit
        payload = [cmd, (speed >> 16) & 0xFF, (speed >> 8) & 0xFF, speed & 0xFF]
        try:
            self._spi.xfer2(payload)
            time.sleep(delay_us * count / 1_000_000)
            self._spi.xfer2([self._CMD_STOP])
        except Exception as exc:  # noqa: BLE001
            logger.error("SPI step error: %s", exc)
        self._position += direction.value * count

    def enable(self) -> None:
        pass

    def disable(self) -> None:
        try:
            self._spi.xfer2([self._CMD_STOP])
        except Exception:  # noqa: BLE001
            pass

    def close(self) -> None:
        self.disable()
        self._spi.close()

    @property
    def position(self) -> int:
        return self._position

    @position.setter
    def position(self, value: int) -> None:
        self._position = value


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def create_driver(
    driver_type: DriverType = "stub",
    **kwargs,
) -> _StubDriver | _GPIODriver | _I2CDriver | _SPIDriver:
    """
    Instantiate the requested motor driver, falling back to the stub on error.
    """
    try:
        if driver_type == "gpio":
            return _GPIODriver(**kwargs)
        if driver_type == "i2c":
            return _I2CDriver(**kwargs)
        if driver_type == "spi":
            return _SPIDriver(**kwargs)
    except RuntimeError as exc:
        logger.warning("Driver '%s' unavailable (%s), using stub", driver_type, exc)
    return _StubDriver()
