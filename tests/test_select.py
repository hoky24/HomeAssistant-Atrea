from unittest.mock import AsyncMock, MagicMock

from pyatrea import AtreaMode, AtreaStatus, CommandBuilder

from custom_components.atrea.models import AtreaData
from custom_components.atrea.select import SELECTS, AtreaModeSelect, AtreaSelect


def coord(regs, supported_modes=None, mode=None):
    c = MagicMock()
    c.data = AtreaData(
        status=AtreaStatus(registers=regs),
        supported_modes=supported_modes or {},
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
    c.client.command_builder.return_value = CommandBuilder()
    c.client.commit = AsyncMock()
    c.client.mode_of.return_value = mode
    c.async_request_refresh = AsyncMock()
    return c


def _d(key):
    return next(d for d in SELECTS if d.key == key)


def test_program_current_and_options():
    e = AtreaSelect(coord({"H10700": "0"}), "e", "A", "1.2.3.4", _d("program"))
    assert e.current_option == "Manual"
    assert set(e.options) == {"Manual", "Schedule", "Temporary"}
    assert e.unique_id == "atrea_1_2_3_4_program"


async def test_program_select_writes():
    co = coord({"H10700": "0"})
    e = AtreaSelect(co, "e", "A", "1.2.3.4", _d("program"))
    await e.async_select_option("Schedule")
    # set_program(WEEKLY) writes H10700=00001
    assert co.client.command_builder.return_value.commands.get("H10700") == "00001"
    co.client.commit.assert_awaited_once()


async def test_zone_select_writes_idw():
    co = coord({"H10707": "0"})
    e = AtreaSelect(co, "e", "A", "1.2.3.4", _d("zone"))
    await e.async_select_option("1+2")
    assert co.client.command_builder.return_value.commands.get("H10717") == "00002"


def test_season_current():
    e = AtreaSelect(coord({"H11401": "1"}), "e", "A", "1.2.3.4", _d("season"))
    assert e.current_option == "non_heating"


def test_count():
    assert len(SELECTS) == 3


def _mode_coord():
    return coord(
        {},
        supported_modes={AtreaMode.VENTILATION: True, AtreaMode.AUTOMATIC: True},
        mode=AtreaMode.VENTILATION,
    )


def test_mode_select_current_and_options():
    e = AtreaModeSelect(_mode_coord(), "e", "A", "1.2.3.4")
    assert e.current_option == "Ventilation"
    assert "Ventilation" in e.options
    assert "Automatic" in e.options
    assert e.unique_id == "atrea_1_2_3_4_operating_mode"


def test_mode_select_options_sorted_by_value():
    e = AtreaModeSelect(_mode_coord(), "e", "A", "1.2.3.4")
    # AtreaMode.AUTOMATIC (value 1) precedes VENTILATION (value 2)
    assert e.options == ["Automatic", "Ventilation"]


async def test_mode_select_writes_mode():
    co = _mode_coord()
    e = AtreaModeSelect(co, "e", "A", "1.2.3.4")
    await e.async_select_option("Automatic")
    co.client.commit.assert_awaited_once()


def test_mode_current_option_none_when_transient():
    # Unit is in a transient regime (DEFROSTING=11) that is NOT in
    # supported_modes, so its label is not a selectable option. The select
    # must report None rather than a label HA would reject as "Invalid option".
    co = coord(
        {},
        supported_modes={AtreaMode.VENTILATION: True, AtreaMode.AUTOMATIC: True},
        mode=AtreaMode.DEFROSTING,
    )
    e = AtreaModeSelect(co, "e", "A", "1.2.3.4")
    assert e.current_option is None
    assert "Defrosting" not in e.options
