"""
sensors.py

Wraps both physical sensors in plain classes. Each class has one job:
talk to its chip, hand back plain Python values (numbers, tuples).
No abstract base classes, no dataclasses -- just readable code.

If you ever swap a sensor for a different model, you only need to
change this file. Everything else in the project just calls
.read_samples() or .read_temperature() and doesn't care what chip
is behind it.
"""

from max30102 import MAX30102  # third-party driver from doug-burrell/max30102
import adafruit_mlx90614

import config


class PulseOxSensor:
    """Wraps the MAX30102. Gives back raw (red, ir) sample pairs."""

    def __init__(self):
        self._sensor = MAX30102()

    def read_samples(self):
        """
        Drains whatever samples are currently sitting in the FIFO buffer
        and returns them as a list of (red, ir) tuples.
        get_data_present() returns how many samples are waiting -- this
        matches the driver's own reference usage.
        """
        samples = []
        num_available = self._sensor.get_data_present()
        while num_available > 0:
            red, ir = self._sensor.read_fifo()
            samples.append((red, ir))
            num_available -= 1
        return samples


class TemperatureSensor:
    """Wraps the MLX90614. Gives back a validated object temperature."""

    def __init__(self, i2c_bus):
        self._mlx = adafruit_mlx90614.MLX90614(i2c_bus)

    def read_temperature(self):
        """
        Returns (object_temp_c, ambient_temp_c).
        object_temp_c is None if the reading is missing or outside a
        plausible human-body range -- this stops a bad reading (sensor
        pointed at the wall, I2C glitch) from ever reaching the display
        as if it were a real number.
        """
        try:
            object_temp = self._mlx.object_temperature
            ambient_temp = self._mlx.ambient_temperature
        except OSError:
            return None, None

        if not (config.TEMP_MIN_PLAUSIBLE_C <= object_temp <= config.TEMP_MAX_PLAUSIBLE_C):
            object_temp = None

        return object_temp, ambient_temp
