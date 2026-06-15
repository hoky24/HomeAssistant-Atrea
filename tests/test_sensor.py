"""Tests for the Atrea sensor platform."""

from unittest.mock import MagicMock

from pyatrea import AtreaStatus
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.atrea.sensor import AtreaSensor, SENSORS
from custom_components.atrea.models import AtreaData


def coord(regs):
    c = MagicMock()
    c.data = AtreaData(
        status=AtreaStatus(registers=regs),
        supported_modes={},
        ids_to_modes={},
        modes_to_ids={},
        forced_modes={},
        user_labels={},
        translations={"params": {}, "words": {}},
        model=None,
        version=None,
        latest_version="0.0",
        unit_id=None,
    )
    return c


def _d(key):
    return next(d for d in SENSORS if d.key == key)


def test_supply_temp():
    e = AtreaSensor(coord({"I10212": "189"}), "e", "Atrea", "1.2.3.4", _d("supply_temp"))
    assert e.native_value == 18.9
    assert e.device_class == SensorDeviceClass.TEMPERATURE
    assert e.state_class == SensorStateClass.MEASUREMENT
    assert e.native_unit_of_measurement == "°C"
    assert e.unique_id == "atrea_1_2_3_4_supply_temp"
    assert e.translation_key == "supply_temp"


def test_efficiency():
    e = AtreaSensor(
        coord({"I10212": "180", "I10211": "0", "I10213": "200"}),
        "e",
        "A",
        "1.2.3.4",
        _d("efficiency"),
    )
    assert e.native_value == 90.0
    assert e.native_unit_of_measurement == "%"


def test_fan_hours_total_increasing():
    e = AtreaSensor(
        coord({"H13500": "20842", "H13501": "0"}),
        "e",
        "A",
        "1.2.3.4",
        _d("fan_hours_m1"),
    )
    assert e.native_value == 20842
    assert e.state_class == SensorStateClass.TOTAL_INCREASING


def test_sensor_count():
    assert len(SENSORS) == 11
