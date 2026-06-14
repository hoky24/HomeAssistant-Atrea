from unittest.mock import AsyncMock, patch

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from pyatrea import AtreaStatus
from pyatrea.exceptions import AtreaAuthError, AtreaConnectionError

from custom_components.atrea.const import DOMAIN


def _client_patch():
    p = patch("custom_components.atrea.config_flow.AtreaClient")
    cls = p.start()
    c = cls.return_value
    c.is_atrea_unit = AsyncMock(return_value=True)
    c.fetch_status = AsyncMock(return_value=AtreaStatus(registers={"H10700": "0"}))
    return p, c


async def test_user_flow_creates_entry(hass):
    p, _ = _client_patch()
    try:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"},
        )
    finally:
        p.stop()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["ip_address"] == "1.2.3.4"


async def test_user_flow_invalid_auth(hass):
    p, c = _client_patch()
    c.fetch_status = AsyncMock(side_effect=AtreaAuthError("denied"))
    try:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"},
        )
    finally:
        p.stop()
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_user_flow_cannot_connect(hass):
    p, c = _client_patch()
    c.is_atrea_unit = AsyncMock(side_effect=AtreaConnectionError("net"))
    try:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"},
        )
    finally:
        p.stop()
    assert result["errors"]["base"] == "cannot_connect"


async def test_duplicate_host_aborts(hass):
    existing = MockConfigEntry(
        domain=DOMAIN, unique_id="1.2.3.4", data={"ip_address": "1.2.3.4", "port": 80}
    )
    existing.add_to_hass(hass)
    p, _ = _client_patch()
    try:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"ip_address": "1.2.3.4", "port": 80, "password": "x", "name": "Atrea"},
        )
    finally:
        p.stop()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
