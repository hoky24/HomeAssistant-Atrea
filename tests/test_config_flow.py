from unittest.mock import AsyncMock, patch

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from pyatrea.exceptions import AtreaAuthError, AtreaConnectionError

from custom_components.atrea.const import DOMAIN


def _http_patch():
    p = patch("custom_components.atrea.config_flow.HttpTransport")
    cls = p.start()
    c = cls.return_value
    c.is_atrea_unit = AsyncMock(return_value=True)
    c.read = AsyncMock(return_value={"H10700": "0"})
    return p, c


async def _start_http(hass):
    """Init the flow and advance the transport-select step to the http step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"transport": "http"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "http"
    return result


async def test_user_flow_creates_entry(hass):
    p, _ = _http_patch()
    try:
        result = await _start_http(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"},
        )
    finally:
        p.stop()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["ip_address"] == "1.2.3.4"
    assert result["data"]["transport"] == "http"


async def test_user_flow_invalid_auth(hass):
    p, c = _http_patch()
    c.read = AsyncMock(side_effect=AtreaAuthError("denied"))
    try:
        result = await _start_http(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"},
        )
    finally:
        p.stop()
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_user_flow_cannot_connect(hass):
    p, c = _http_patch()
    c.is_atrea_unit = AsyncMock(side_effect=AtreaConnectionError("net"))
    try:
        result = await _start_http(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"},
        )
    finally:
        p.stop()
    assert result["errors"]["base"] == "cannot_connect"


async def test_modbus_flow_creates_entry(hass):
    with patch("custom_components.atrea.config_flow.ModbusTransport") as mt:
        inst = mt.return_value
        inst.connect = AsyncMock()
        inst.is_atrea_unit = AsyncMock(return_value=True)
        inst.read = AsyncMock(return_value={"H10705": "2"})
        inst.close = AsyncMock()
        r = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"], {"transport": "modbus"}
        )
        assert r["type"] is FlowResultType.FORM
        assert r["step_id"] == "modbus"
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"],
            {"ip_address": "1.2.3.4", "port": 502, "slave_id": 1, "name": "Atrea"},
        )
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["data"]["transport"] == "modbus"
    assert r["data"]["slave_id"] == 1


async def test_modbus_flow_cannot_connect(hass):
    with patch("custom_components.atrea.config_flow.ModbusTransport") as mt:
        inst = mt.return_value
        inst.connect = AsyncMock(side_effect=AtreaConnectionError("refused"))
        inst.is_atrea_unit = AsyncMock(return_value=True)
        inst.read = AsyncMock(return_value={})
        inst.close = AsyncMock()
        r = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"], {"transport": "modbus"}
        )
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"],
            {"ip_address": "1.2.3.4", "port": 502, "slave_id": 1, "name": "Atrea"},
        )
    assert r["type"] is FlowResultType.FORM
    assert r["errors"]["base"] == "cannot_connect"


async def test_duplicate_host_aborts(hass):
    existing = MockConfigEntry(
        domain=DOMAIN, unique_id="1.2.3.4", data={"ip_address": "1.2.3.4", "port": 80}
    )
    existing.add_to_hass(hass)
    p, _ = _http_patch()
    try:
        result = await _start_http(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"},
        )
    finally:
        p.stop()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


def test_options_flow_uses_reload_subclass():
    """OptionsFlow must subclass OptionsFlowWithReload so saved options reload
    the entry automatically (HA 2024.11+)."""
    from homeassistant.config_entries import OptionsFlowWithReload

    from custom_components.atrea.config_flow import AtreaOptionsFlow

    assert issubclass(AtreaOptionsFlow, OptionsFlowWithReload)


async def test_options_flow_creates_entry(hass):
    from custom_components.atrea.const import CONF_FAN_MODES, CONF_PRESETS

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={"ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_FAN_MODES: "12,50,100"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_FAN_MODES] == "12,50,100"
    assert CONF_PRESETS in result["data"]


async def test_reconfigure_flow_updates_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id="1.2.3.4",
        data={"ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"},
    )
    entry.add_to_hass(hass)
    p, _ = _http_patch()
    try:
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "ip_address": "1.2.3.4",
                "port": 81,
                "password": "y",
                "name": "Atrea",
            },
        )
    finally:
        p.stop()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["port"] == 81
    assert entry.data["password"] == "y"


async def test_reconfigure_flow_invalid_auth(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id="1.2.3.4",
        data={"ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"},
    )
    entry.add_to_hass(hass)
    p, c = _http_patch()
    c.read = AsyncMock(side_effect=AtreaAuthError("denied"))
    try:
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "ip_address": "1.2.3.4",
                "port": 80,
                "password": "bad",
                "name": "Atrea",
            },
        )
    finally:
        p.stop()
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"
