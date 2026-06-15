"""Tests for the Atrea sensor platform."""

from unittest.mock import MagicMock

from pyatrea import AtreaStatus
from pyatrea.registers import by_role
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.atrea.sensor import (
    AtreaActiveFlagsSensor,
    AtreaSensor,
    SENSORS,
)
from custom_components.atrea.models import AtreaData


def coord(regs, tr=None):
    c = MagicMock()
    c.data = AtreaData(
        status=AtreaStatus(registers=regs),
        supported_modes={},
        ids_to_modes={},
        modes_to_ids={},
        forced_modes={},
        user_labels={},
        translations=tr or {"params": {}, "words": {}},
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


def test_active_warnings_label():
    wid = by_role("warning")[0]
    tr = {"params": {wid: {"t": "Test%20warning"}}, "words": {}}
    e = AtreaActiveFlagsSensor(
        coord({wid: "1"}, tr), "e", "A", "1.2.3.4", "warning", "active_warnings"
    )
    assert e.native_value == "Test warning"
    assert e.extra_state_attributes["active"] == ["Test warning"]
    assert e.unique_id == "atrea_1_2_3_4_active_warnings"
    assert e.translation_key == "active_warnings"
    assert e.device_class is None
    assert e.state_class is None


def test_active_warnings_multiple_joined():
    wids = by_role("warning")
    tr = {
        "params": {
            wids[0]: {"t": "First"},
            wids[1]: {"t": "Second"},
        },
        "words": {},
    }
    e = AtreaActiveFlagsSensor(
        coord({wids[0]: "1", wids[1]: "1"}, tr),
        "e",
        "A",
        "1.2.3.4",
        "warning",
        "active_warnings",
    )
    assert e.native_value == "First, Second"


def test_active_warnings_ok_when_none():
    e = AtreaActiveFlagsSensor(
        coord({}), "e", "A", "1.2.3.4", "warning", "active_warnings"
    )
    assert e.native_value == "OK"
    assert e.extra_state_attributes["active"] == []


def test_active_alerts_label():
    aid = by_role("alert")[0]
    tr = {"params": {aid: {"t": "Test%20alert"}}, "words": {}}
    e = AtreaActiveFlagsSensor(
        coord({aid: "1"}, tr), "e", "A", "1.2.3.4", "alert", "active_alerts"
    )
    assert e.native_value == "Test alert"
    assert e.unique_id == "atrea_1_2_3_4_active_alerts"
    assert e.translation_key == "active_alerts"


def test_active_alerts_ok_when_none():
    e = AtreaActiveFlagsSensor(
        coord({}), "e", "A", "1.2.3.4", "alert", "active_alerts"
    )
    assert e.native_value == "OK"


def test_active_flags_none_status():
    c = MagicMock()
    c.data = None
    e = AtreaActiveFlagsSensor(c, "e", "A", "1.2.3.4", "warning", "active_warnings")
    assert e.native_value is None
    assert e.extra_state_attributes is None
