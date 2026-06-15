from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pyatrea import AtreaConnectionError, AtreaMode, AtreaStatus, CommandBuilder

from custom_components.atrea.models import AtreaData
from custom_components.atrea.services import _apply_to_coordinator


def coord(supported_modes=None):
    c = MagicMock()
    c.data = AtreaData(
        status=AtreaStatus(registers={}),
        supported_modes=supported_modes
        or {AtreaMode.OFF: True, AtreaMode.VENTILATION: True},
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
    c.async_request_refresh = AsyncMock()
    return c


async def test_empty_fields_raises():
    co = coord()
    with pytest.raises(ServiceValidationError):
        await _apply_to_coordinator(co)
    co.client.commit.assert_not_awaited()


async def test_unknown_mode_raises():
    co = coord()
    with pytest.raises(ServiceValidationError):
        await _apply_to_coordinator(co, mode="Nonexistent")
    co.client.commit.assert_not_awaited()


async def test_mode_not_supported_raises():
    # "Automatic" is a valid AtreaMode display name but not in supported_modes.
    co = coord(supported_modes={AtreaMode.OFF: True, AtreaMode.VENTILATION: True})
    with pytest.raises(ServiceValidationError):
        await _apply_to_coordinator(co, mode="Automatic")
    co.client.commit.assert_not_awaited()


async def test_program_and_mode_in_one_commit():
    co = coord()
    await _apply_to_coordinator(co, program="manual", mode="Off")
    builder = co.client.command_builder.return_value
    # set_program(MANUAL) stages the H10700 program family in the SAME builder...
    assert builder.commands.get("H10700") == "00000"
    assert builder.commands.get("H10701") == "00000"
    # ...and set_mode(OFF) stages the OFF mode registers in that same builder.
    assert "H10709" in builder.commands
    assert builder.commands.get("H01019") == "00000"
    co.client.commit.assert_awaited_once()
    co.async_request_refresh.assert_awaited_once()


async def test_power_writes_register():
    co = coord()
    await _apply_to_coordinator(co, power=80)
    assert co.client.command_builder.return_value.commands.get("H10708") == "00080"
    co.client.commit.assert_awaited_once()


async def test_target_temperature_writes_register():
    co = coord()
    await _apply_to_coordinator(co, target_temperature=22)
    assert co.client.command_builder.return_value.commands.get("H10710") == "00220"
    co.client.commit.assert_awaited_once()


async def test_connection_error_wrapped():
    co = coord()
    co.client.commit = AsyncMock(side_effect=AtreaConnectionError("boom"))
    with pytest.raises(HomeAssistantError):
        await _apply_to_coordinator(co, power=80)
    co.async_request_refresh.assert_not_awaited()
