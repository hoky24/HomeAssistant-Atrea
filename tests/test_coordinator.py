from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pyatrea import AtreaMode, AtreaStatus
from pyatrea.exceptions import AtreaAuthError, AtreaConnectionError

from custom_components.atrea.coordinator import AtreaDataUpdateCoordinator


def make_client():
    c = MagicMock()
    status = AtreaStatus(registers={"H10700": "0", "H10705": "2"})
    c.fetch_status = AsyncMock(return_value=status)
    c.fetch_userctrl = AsyncMock(
        return_value=({AtreaMode.VENTILATION: True}, {}, {}, {})
    )
    c.fetch_config_dir = AsyncMock(return_value=None)
    c.fetch_user_labels = AsyncMock(return_value={})
    c.fetch_translations = AsyncMock(return_value={"params": {}, "words": {}})
    c.model_of.return_value = None
    c.version_of.return_value = "2.0.1"
    c.latest_version_of.return_value = "0.0"
    c.id_of.return_value = None
    return c, status


async def test_update_builds_data(hass):
    client, status = make_client()
    coord = AtreaDataUpdateCoordinator(hass, client)
    data = await coord._async_update_data()
    assert data.status is status
    assert data.supported_modes == {AtreaMode.VENTILATION: True}
    assert data.version == "2.0.1"


async def test_static_data_fetched_once(hass):
    client, _ = make_client()
    coord = AtreaDataUpdateCoordinator(hass, client)
    await coord._async_update_data()
    await coord._async_update_data()
    # config_dir/translations/user_labels fetched only on the first cycle
    assert client.fetch_config_dir.await_count == 1
    assert client.fetch_translations.await_count == 1
    assert client.fetch_user_labels.await_count == 1
    # userctrl is firmware-static: fetched only on the first cycle
    assert client.fetch_userctrl.await_count == 1
    # status fetched every cycle (bitmask overlay recomputed per cycle)
    assert client.fetch_status.await_count == 2


async def test_partial_poll_retains_previous_registers(hass):
    client, _ = make_client()
    coord = AtreaDataUpdateCoordinator(hass, client)
    client.fetch_status = AsyncMock(
        return_value=AtreaStatus(registers={"I10215": "215", "H10700": "0"})
    )
    d1 = await coord._async_update_data()
    coord.async_set_updated_data(d1)  # mimic coordinator storing data
    # next poll is partial: I10215 missing
    client.fetch_status = AsyncMock(return_value=AtreaStatus(registers={"H10700": "0"}))
    d2 = await coord._async_update_data()
    assert d2.status.registers.get("I10215") == "215"  # retained


async def test_invalidate_static_forces_refetch(hass):
    client, _ = make_client()
    coord = AtreaDataUpdateCoordinator(hass, client)
    await coord._async_update_data()
    assert client.fetch_userctrl.await_count == 1
    coord.invalidate_static()
    await coord._async_update_data()
    # static data re-fetched after invalidation
    assert client.fetch_userctrl.await_count == 2
    assert client.fetch_config_dir.await_count == 2


async def test_auth_error_maps_to_configentryauthfailed(hass):
    client, _ = make_client()
    client.fetch_status = AsyncMock(side_effect=AtreaAuthError("denied"))
    coord = AtreaDataUpdateCoordinator(hass, client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()


async def test_connection_error_maps_to_updatefailed(hass):
    client, _ = make_client()
    client.fetch_status = AsyncMock(side_effect=AtreaConnectionError("net"))
    coord = AtreaDataUpdateCoordinator(hass, client)
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
