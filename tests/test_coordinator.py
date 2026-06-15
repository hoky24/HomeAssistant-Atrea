from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed
from pyatrea import AtreaMode, AtreaStatus, Descriptors
from pyatrea.exceptions import AtreaAuthError, AtreaConnectionError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.atrea.const import DOMAIN
from custom_components.atrea.coordinator import AtreaDataUpdateCoordinator

# What the patched AtreaClient.supported_from returns: writable map + 3 mode maps.
_SUPPORTED = ({AtreaMode.VENTILATION: True}, {}, {}, {})


def make_client():
    c = MagicMock()
    status = AtreaStatus(registers={"H10700": "0", "H10705": "2"})
    c.fetch_status = AsyncMock(return_value=status)
    c.fetch_descriptors = AsyncMock(
        return_value=Descriptors(user_labels={}, translations={"params": {}, "words": {}})
    )
    c.model_of.return_value = None
    c.version_of.return_value = "2.0.1"
    c.latest_version_of.return_value = "0.0"
    c.id_of.return_value = None
    return c, status


async def test_update_builds_data(hass):
    client, status = make_client()
    coord = AtreaDataUpdateCoordinator(hass, client)
    with patch(
        "custom_components.atrea.coordinator.AtreaClient.supported_from",
        return_value=_SUPPORTED,
    ):
        data = await coord._async_update_data()
    assert data.status is status
    # supported_modes is derived per cycle via supported_from(status, descriptors)
    assert data.supported_modes == {AtreaMode.VENTILATION: True}
    assert data.version == "2.0.1"


async def test_static_data_fetched_once(hass):
    client, _ = make_client()
    coord = AtreaDataUpdateCoordinator(hass, client)
    with patch(
        "custom_components.atrea.coordinator.AtreaClient.supported_from",
        return_value=_SUPPORTED,
    ) as supported_from:
        await coord._async_update_data()
        await coord._async_update_data()
    # descriptors are firmware-static: fetched only on the first cycle
    assert client.fetch_descriptors.await_count == 1
    # status fetched every cycle; supported_from recomputed per cycle
    assert client.fetch_status.await_count == 2
    assert supported_from.call_count == 2


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
    assert client.fetch_descriptors.await_count == 1
    coord.invalidate_static()
    await coord._async_update_data()
    # static descriptors re-fetched after invalidation
    assert client.fetch_descriptors.await_count == 2


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


def _entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Atrea",
        data={"ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"},
    )
    entry.add_to_hass(hass)
    return entry


async def test_repair_issue_after_consecutive_failures(hass):
    client, _ = make_client()
    client.fetch_status = AsyncMock(side_effect=AtreaConnectionError("net"))
    entry = _entry(hass)
    coord = AtreaDataUpdateCoordinator(hass, client, config_entry=entry)

    registry = ir.async_get(hass)
    issue_id = f"unreachable_{entry.entry_id}"

    # Below threshold: no issue yet.
    for _ in range(4):
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
    assert registry.async_get_issue(DOMAIN, issue_id) is None

    # 5th consecutive failure crosses the threshold: issue raised.
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    issue = registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_key == "unit_unreachable"
    assert issue.translation_placeholders == {"name": "Atrea"}
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.is_fixable is False


async def test_repair_issue_cleared_on_recovery(hass):
    client, status = make_client()
    client.fetch_status = AsyncMock(side_effect=AtreaConnectionError("net"))
    entry = _entry(hass)
    coord = AtreaDataUpdateCoordinator(hass, client, config_entry=entry)
    registry = ir.async_get(hass)
    issue_id = f"unreachable_{entry.entry_id}"

    for _ in range(5):
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
    assert registry.async_get_issue(DOMAIN, issue_id) is not None

    # Recovery: a successful poll clears the issue.
    client.fetch_status = AsyncMock(return_value=status)
    await coord._async_update_data()
    assert registry.async_get_issue(DOMAIN, issue_id) is None


async def test_auth_failure_does_not_raise_repair(hass):
    client, _ = make_client()
    client.fetch_status = AsyncMock(side_effect=AtreaAuthError("denied"))
    entry = _entry(hass)
    coord = AtreaDataUpdateCoordinator(hass, client, config_entry=entry)
    registry = ir.async_get(hass)
    issue_id = f"unreachable_{entry.entry_id}"

    for _ in range(6):
        with pytest.raises(ConfigEntryAuthFailed):
            await coord._async_update_data()
    # Auth is handled by reauth, not a repair issue.
    assert registry.async_get_issue(DOMAIN, issue_id) is None


async def test_repair_issue_without_config_entry(hass):
    client, _ = make_client()
    client.fetch_status = AsyncMock(side_effect=AtreaConnectionError("net"))
    coord = AtreaDataUpdateCoordinator(hass, client)
    registry = ir.async_get(hass)

    for _ in range(5):
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
    # Falls back to a constant entry_id; an issue is still created and named.
    issue = registry.async_get_issue(DOMAIN, "unreachable_unknown")
    assert issue is not None
    assert issue.translation_placeholders == {"name": "Atrea"}
