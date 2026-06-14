from unittest.mock import MagicMock
from pyatrea import AtreaStatus, AtreaMode, AtreaProgram
from homeassistant.components.climate import HVACMode
from custom_components.atrea.climate import AtreaClimate
from custom_components.atrea.models import AtreaData


def make_coordinator(registers, program=AtreaProgram.WEEKLY, mode=AtreaMode.VENTILATION):
    coord = MagicMock()
    coord.data = AtreaData(
        status=AtreaStatus(registers=registers),
        supported_modes={AtreaMode.VENTILATION: True}, ids_to_modes={},
        modes_to_ids={}, forced_modes={}, user_labels={},
        translations={"params": {}, "words": {}}, model=None, version=None,
        latest_version="0.0", unit_id=None)
    coord.client.program_of.return_value = program
    coord.client.mode_of.return_value = mode
    coord.client.forced_mode_of.return_value = AtreaMode.OFF
    return coord


def entity(coord, fan_list="12,100"):
    return AtreaClimate(coord, "e", "Atrea", "1.2.3.4", fan_list, {})


def test_hvac_mode_auto_when_weekly():
    e = entity(make_coordinator({"H10700": "1"}, program=AtreaProgram.WEEKLY))
    assert e.hvac_mode == HVACMode.AUTO


def test_preset_mode_never_raises_when_mode_none():
    coord = make_coordinator({}, mode=None)
    coord.client.mode_of.return_value = None
    e = entity(coord)
    assert e.preset_mode is not None  # returns a string / STATE_UNKNOWN, never raises


def test_extra_state_attributes_survive_none_forced_mode():
    coord = make_coordinator({"I10215": "215"})
    e = entity(coord)
    attrs = e.extra_state_attributes  # must not raise
    assert "inside_temp" in attrs


def test_fan_modes_expanded_to_full_granularity():
    e = entity(make_coordinator({}), fan_list="12,20,30,40,50,60,70,80,90,100")
    # coarse list (<80 entries) → expanded to per-1% 12..100 (89 entries)
    assert len(e.fan_modes) == 89
    assert "25%" in e.fan_modes
