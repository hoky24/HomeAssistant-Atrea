from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pyatrea import AtreaStatus
from custom_components.atrea.const import DOMAIN


def _patched_client():
    p = patch("custom_components.atrea.AtreaClient")
    cls = p.start()
    client = cls.return_value
    client.fetch_status = AsyncMock(return_value=AtreaStatus(registers={"H10700": "0"}))
    client.fetch_supported = AsyncMock(return_value=({}, {}, {}, {}))
    client.fetch_config_dir = AsyncMock(return_value=None)
    client.fetch_translations = AsyncMock(return_value={"params": {}, "words": {}})
    client.fetch_user_labels = AsyncMock(return_value={})
    client.model_of.return_value = None
    client.version_of.return_value = "2.0.1"
    client.latest_version_of.return_value = "0.0"
    client.id_of.return_value = None
    return p, client


async def test_setup_entry_creates_runtime_data(hass, request):
    entry = MockConfigEntry(domain=DOMAIN, version=2, data={
        "ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"})
    entry.add_to_hass(hass)
    p, _ = _patched_client()
    request.addfinalizer(p.stop)
    # avoid loading the not-yet-rewritten climate/update platforms
    with patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
               AsyncMock(return_value=True)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.coordinator is not None
    assert entry.runtime_data.client is not None


async def test_setup_entry_auth_failure_aborts(hass, request):
    from pyatrea.exceptions import AtreaAuthError
    entry = MockConfigEntry(domain=DOMAIN, version=2, data={
        "ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"})
    entry.add_to_hass(hass)
    p, client = _patched_client()
    request.addfinalizer(p.stop)
    client.fetch_status = AsyncMock(side_effect=AtreaAuthError("denied"))
    # the not-yet-rewritten config_flow has no reauth step; suppress the reauth
    # flow so the test stays focused on async_setup_entry's auth handling
    with patch.object(type(entry), "async_start_reauth", MagicMock()):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    # ConfigEntryAuthFailed from first refresh → SETUP_ERROR (reauth) state
    assert entry.state in (ConfigEntryState.SETUP_ERROR, ConfigEntryState.SETUP_RETRY)
