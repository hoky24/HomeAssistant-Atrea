from unittest.mock import MagicMock
from pyatrea import AtreaStatus
from pyatrea.registers import by_role
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from custom_components.atrea.binary_sensor import AtreaBinarySensor, BINARY_SENSORS
from custom_components.atrea.models import AtreaData


def coord(regs, tr=None):
    c = MagicMock()
    c.data = AtreaData(status=AtreaStatus(registers=regs), supported_modes={},
                       ids_to_modes={}, modes_to_ids={}, forced_modes={}, user_labels={},
                       translations=tr or {"params": {}, "words": {}}, model=None,
                       version=None, latest_version="0.0", unit_id=None)
    return c


def _d(key):
    return next(d for d in BINARY_SENSORS if d.key == key)


def test_filter_problem():
    e = AtreaBinarySensor(coord({"D11183": "1"}), "e", "A", "1.2.3.4", _d("filter"))
    assert e.is_on is True
    assert e.device_class == BinarySensorDeviceClass.PROBLEM
    assert e.unique_id == "atrea_1_2_3_4_filter"


def test_any_warning_active_attr():
    wid = by_role("warning")[0]
    tr = {"params": {wid: {"t": "Test%20warning"}}, "words": {}}
    e = AtreaBinarySensor(coord({wid: "1"}, tr), "e", "A", "1.2.3.4", _d("any_warning"))
    assert e.is_on is True
    assert e.extra_state_attributes["active"] == ["Test warning"]


def test_heating_off_and_none_safe():
    assert AtreaBinarySensor(coord({"C10215": "0"}), "e", "A", "1.2.3.4", _d("heating")).is_on is False


def test_defrost_any():
    assert AtreaBinarySensor(coord({"D11118": "1"}), "e", "A", "1.2.3.4", _d("defrost")).is_on is True


def test_count():
    assert len(BINARY_SENSORS) == 6
