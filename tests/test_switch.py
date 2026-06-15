from unittest.mock import AsyncMock, MagicMock

from pyatrea import AtreaStatus, CommandBuilder

from custom_components.atrea.models import AtreaData
from custom_components.atrea.switch import AtreaNightPrecooling


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


def test_is_on():
    assert AtreaNightPrecooling(coord({"C10902": "1"}), "e", "A", "1.2.3.4").is_on is True
    assert AtreaNightPrecooling(coord({"C10902": "0"}), "e", "A", "1.2.3.4").is_on is False


async def test_turn_on_writes_coil():
    co = coord({"C10902": "0"})
    e = AtreaNightPrecooling(co, "e", "A", "1.2.3.4")
    await e.async_turn_on()
    assert co.client.command_builder.return_value.commands.get("C10902") == "00001"
    co.client.commit.assert_awaited_once()
