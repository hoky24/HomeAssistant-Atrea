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


def test_preset_modes_from_supported():
    e = AtreaFan(coord({}), "e", "A", "1.2.3.4")
    assert "Ventilation" in e.preset_modes and "Automatic" in e.preset_modes


def test_preset_mode_current():
    e = AtreaFan(coord({}, mode=AtreaMode.VENTILATION), "e", "A", "1.2.3.4")
    assert e.preset_mode == "Ventilation"


async def test_set_percentage_writes_power():
    co = coord({"H10704": "30"})
    e = AtreaFan(co, "e", "A", "1.2.3.4")
    await e.async_set_percentage(40)
    assert co.client.command_builder.return_value.commands.get("H10708") == "00040"
    co.client.commit.assert_awaited_once()


async def test_set_preset_writes_mode():
    co = coord({}, mode=AtreaMode.VENTILATION)
    e = AtreaFan(co, "e", "A", "1.2.3.4")
    await e.async_set_preset_mode("Automatic")
    co.client.commit.assert_awaited_once()
