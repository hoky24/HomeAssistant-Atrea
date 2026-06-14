from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from pyatrea import AtreaStatus, AtreaMode, AtreaProgram, AtreaParams, CommandBuilder
from homeassistant.components.climate import HVACMode
from homeassistant.const import ATTR_TEMPERATURE
from custom_components.atrea.climate import AtreaClimate, async_setup_entry
from custom_components.atrea.const import CONF_FAN_MODES
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


def test_climate_reads_fan_modes_from_options():
    # options override data for fan/preset config
    coord = make_coordinator({})
    # simulate async_setup_entry's merge: build entity with an options-derived list
    e = AtreaClimate(coord, "e", "Atrea", "1.2.3.4", "12,20,30,40,50", {})
    # coarse list still expands per the 1% contract (existing behaviour) -> 89
    assert len(e.fan_modes) == 89


async def test_setup_entry_merges_options_over_data():
    """async_setup_entry must read CONF_FAN_MODES from {**data, **options}.

    data carries a coarse list (would expand to 89); options carries a fine
    list (>= 80 entries, passes through unchanged at its own length). If the
    merge consults options, the fine list wins -> 81, not 89.
    """
    coord = make_coordinator({})
    fine_list = ",".join(str(i) for i in range(20, 101))  # 81 entries, >= 80
    entry = SimpleNamespace(
        entry_id="e",
        runtime_data=SimpleNamespace(coordinator=coord),
        data={"ip_address": "1.2.3.4", "name": "Atrea", CONF_FAN_MODES: "12,50,100"},
        options={CONF_FAN_MODES: fine_list},
    )
    created: list[AtreaClimate] = []
    await async_setup_entry(None, entry, lambda ents: created.extend(ents))
    assert len(created) == 1
    # options' fine list (81 entries) wins over data's coarse list (would be 89)
    assert len(created[0].fan_modes) == 81


def test_hvac_action_property_reports_heating():
    coord = make_coordinator({"C10215": "1"})  # heating on
    e = entity(coord)
    from homeassistant.components.climate import HVACAction
    assert e.hvac_action == HVACAction.HEATING


def writable_coord(program=AtreaProgram.MANUAL):
    coord = make_coordinator({"H10708": "0", "H01020": "0", "H10700": "0"},
                             program=program)
    builder = CommandBuilder(
        params=AtreaParams(ids=["H10708", "H01020", "H10700", "H10701",
                                "H10702", "H10703", "H01015", "H01016", "H01017"]),
        known_registers={"H10708", "H01020", "H10700", "H10701", "H10702",
                         "H10703", "H01015", "H01016", "H01017"})
    coord.client.command_builder.return_value = builder
    coord.client.commit = AsyncMock(return_value=True)
    coord.async_request_refresh = AsyncMock()
    return coord, builder


async def test_set_fan_mode_commits_and_refreshes():
    coord, builder = writable_coord(program=AtreaProgram.MANUAL)
    e = entity(coord)
    await e.async_set_fan_mode("40%")
    assert builder.commands.get("H10708") == "00040"
    coord.client.commit.assert_awaited_once()
    coord.async_request_refresh.assert_awaited_once()


async def test_set_fan_mode_on_weekly_switches_to_temporary():
    coord, builder = writable_coord(program=AtreaProgram.WEEKLY)
    e = entity(coord)
    await e.async_set_fan_mode("40%")
    # WEEKLY → TEMPORARY: H10700 set to 2
    assert builder.commands.get("H10700") == "00002"


def test_temp_registers_ignore_coef_offset_like_legacy():
    coord = make_coordinator({"I10215": "215"})
    # real unit has coef=10 on I10215; legacy read it RAW and /10 -> 21.5
    coord.data.status = AtreaStatus(registers={"I10215": "215"},
                                    params=AtreaParams(coefs={"I10215": 10.0}))
    e = entity(coord)
    attrs = e.extra_state_attributes
    assert attrs["inside_temp"] == 21.5   # NOT 2.15


def test_outside_temp_negative_sentinel_uses_raw():
    coord = make_coordinator({"I10211": "65136"})
    coord.data.status = AtreaStatus(registers={"I10211": "65136"},
                                    params=AtreaParams(coefs={"I10211": 10.0}))
    e = entity(coord)
    # raw 65136 > 1300 -> (50 - (65136-65036)/10) * -1 = (50 - 10)*-1 = -40.0
    assert e.extra_state_attributes["outside_temp"] == -40.0


async def test_set_temperature_commits():
    coord, builder = writable_coord()
    builder.params.ids.extend(["H10710", "H01021"])
    builder.known_registers.update({"H10710", "H01021"})
    e = entity(coord)
    await e.async_set_temperature(**{ATTR_TEMPERATURE: 22})
    assert builder.commands.get("H10710") == "00220"
    coord.client.commit.assert_awaited_once()
