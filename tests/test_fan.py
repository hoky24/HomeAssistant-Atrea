from unittest.mock import AsyncMock, MagicMock
from pyatrea import AtreaStatus, CommandBuilder, AtreaMode
from custom_components.atrea.fan import AtreaFan
from custom_components.atrea.models import AtreaData


def coord(regs, mode=AtreaMode.VENTILATION):
    c = MagicMock()
    c.data = AtreaData(status=AtreaStatus(registers=regs),
                       supported_modes={AtreaMode.VENTILATION: True, AtreaMode.AUTOMATIC: True},
                       ids_to_modes={}, modes_to_ids={}, forced_modes={}, user_labels={},
                       translations={"params": {}, "words": {}}, model=None, version=None,
                       latest_version="0.0", unit_id=None)
    c.client.mode_of.return_value = mode
    c.client.command_builder.return_value = CommandBuilder()
    c.client.commit = AsyncMock()
    c.async_request_refresh = AsyncMock()
    return c


def test_percentage_from_power():
    e = AtreaFan(coord({"H10704": "48"}), "e", "A", "1.2.3.4")
    assert e.percentage == 48


def test_no_preset_mode_feature():
    from homeassistant.components.fan import FanEntityFeature

    e = AtreaFan(coord({}), "e", "A", "1.2.3.4")
    assert not (e.supported_features & FanEntityFeature.PRESET_MODE)
    assert e.supported_features & FanEntityFeature.SET_SPEED
    assert not hasattr(e, "preset_modes") or not callable(
        getattr(type(e), "preset_modes", None)
    )


async def test_set_percentage_writes_power():
    co = coord({"H10704": "30"})
    e = AtreaFan(co, "e", "A", "1.2.3.4")
    await e.async_set_percentage(40)
    assert co.client.command_builder.return_value.commands.get("H10708") == "00040"
    co.client.commit.assert_awaited_once()


async def test_turn_on_default_minimum():
    co = coord({"H10704": "0"})
    e = AtreaFan(co, "e", "A", "1.2.3.4")
    await e.async_turn_on()
    assert co.client.command_builder.return_value.commands.get("H10708") == "00012"
    co.client.commit.assert_awaited_once()


async def test_turn_off_writes_off_mode():
    co = coord({"H10704": "40"})
    e = AtreaFan(co, "e", "A", "1.2.3.4")
    await e.async_turn_off()
    co.client.commit.assert_awaited_once()
