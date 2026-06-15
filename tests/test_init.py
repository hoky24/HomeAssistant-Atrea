from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pyatrea import AtreaStatus, Descriptors
from custom_components.atrea.const import DOMAIN


def _patched_client():
    """Patch the AtreaClient class and both transports for v3 setup.

    Returns the started patchers plus the stubbed client instance. The client
    is built from a transport now, so the transports are patched to no-ops and
    the v3 static mappers / fetch_* coroutines are stubbed.
    """
    patchers = [
        patch("custom_components.atrea.AtreaClient"),
        patch("custom_components.atrea.HttpTransport"),
        patch("custom_components.atrea.ModbusTransport"),
    ]
    client_cls = patchers[0].start()
    http_cls = patchers[1].start()
    modbus_cls = patchers[2].start()
    # supported_from is a static method the coordinator unpacks into 4 maps.
    client_cls.supported_from.return_value = ({}, {}, {}, {})
    client = client_cls.return_value
    client.fetch_status = AsyncMock(return_value=AtreaStatus(registers={"H10700": "0"}))
    client.fetch_descriptors = AsyncMock(return_value=Descriptors())
    client.model_of.return_value = None
    client.version_of.return_value = "2.0.1"
    client.latest_version_of.return_value = "0.0"
    client.id_of.return_value = None

    def _stop():
        for p in patchers:
            p.stop()

    return _stop, client, http_cls, modbus_cls


async def test_setup_entry_creates_runtime_data(hass, request):
    entry = MockConfigEntry(domain=DOMAIN, version=2, data={
        "ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"})
    entry.add_to_hass(hass)
    stop, _, _http, _modbus = _patched_client()
    request.addfinalizer(stop)
    # avoid loading the not-yet-rewritten climate/update platforms
    with patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
               AsyncMock(return_value=True)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.coordinator is not None
    assert entry.runtime_data.client is not None


async def test_setup_entry_builds_http_transport(hass, request):
    """A legacy/http entry must construct an HttpTransport (not Modbus)."""
    entry = MockConfigEntry(domain=DOMAIN, version=2, data={
        "ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"})
    entry.add_to_hass(hass)
    stop, _, http_cls, modbus_cls = _patched_client()
    request.addfinalizer(stop)
    with patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
               AsyncMock(return_value=True)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    http_cls.assert_called_once()
    modbus_cls.assert_not_called()


async def test_setup_entry_builds_modbus_transport(hass, request):
    """A transport=modbus entry must construct a ModbusTransport."""
    entry = MockConfigEntry(domain=DOMAIN, version=2, data={
        "ip_address": "1.2.3.4", "port": 502, "transport": "modbus",
        "slave_id": 3, "name": "Atrea"})
    entry.add_to_hass(hass)
    stop, _, http_cls, modbus_cls = _patched_client()
    request.addfinalizer(stop)
    with patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
               AsyncMock(return_value=True)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    modbus_cls.assert_called_once_with("1.2.3.4", 502, 3)
    http_cls.assert_not_called()


async def test_setup_entry_auth_failure_aborts(hass, request):
    from pyatrea.exceptions import AtreaAuthError
    entry = MockConfigEntry(domain=DOMAIN, version=2, data={
        "ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"})
    entry.add_to_hass(hass)
    stop, client, _http, _modbus = _patched_client()
    request.addfinalizer(stop)
    client.fetch_status = AsyncMock(side_effect=AtreaAuthError("denied"))
    # the not-yet-rewritten config_flow has no reauth step; suppress the reauth
    # flow so the test stays focused on async_setup_entry's auth handling
    with patch.object(type(entry), "async_start_reauth", MagicMock()):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    # ConfigEntryAuthFailed from first refresh → SETUP_ERROR (reauth) state
    assert entry.state in (ConfigEntryState.SETUP_ERROR, ConfigEntryState.SETUP_RETRY)
