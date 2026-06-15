from unittest.mock import AsyncMock, MagicMock

from pyatrea import AtreaStatus, CommandBuilder

from custom_components.atrea.models import AtreaData
from custom_components.atrea.number import AtreaTargetTemperature


def coord(regs):
    c = MagicMock()
    c.data = AtreaData(status=AtreaStatus(registers=regs), supported_modes={}, ids_to_modes={},
                       modes_to_ids={}, forced_modes={}, user_labels={},
                       translations={"params": {}, "words": {}}, model=None, version=None,
                       latest_version="0.0", unit_id=None)
    c.client.command_builder.return_value = CommandBuilder()
    c.client.commit = AsyncMock()
    c.async_request_refresh = AsyncMock()
    return c


def test_native_value_scales():
    assert AtreaTargetTemperature(coord({"H10706": "230"}), "e", "A", "1.2.3.4").native_value == 23.0


async def test_set_value_writes_temperature():
    co = coord({"H10706": "230"})
    e = AtreaTargetTemperature(co, "e", "A", "1.2.3.4")
    await e.async_set_native_value(22.0)
    assert co.client.command_builder.return_value.commands.get("H10710") == "00220"
    co.client.commit.assert_awaited_once()
    co.async_request_refresh.assert_awaited_once()
