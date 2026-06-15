from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pyatrea import AtreaMode, AtreaStatus

from custom_components.atrea.const import DOMAIN
from custom_components.atrea.diagnostics import (
    async_get_config_entry_diagnostics,
)


def _patched_client():
    p = patch("custom_components.atrea.AtreaClient")
    cls = p.start()
    client = cls.return_value
    client.fetch_status = AsyncMock(
        return_value=AtreaStatus(registers={"H10700": "0", "I10211": "215"})
    )
    client.fetch_userctrl = AsyncMock(
        return_value=(
            {AtreaMode.VENTILATION: True},
            {},
            {},
            {1: AtreaMode.IN1},
        )
    )
    client.fetch_config_dir = AsyncMock(return_value=None)
    client.fetch_translations = AsyncMock(return_value={"params": {}, "words": {}})
    client.fetch_user_labels = AsyncMock(return_value={})
    client.model_of.return_value = None
    client.version_of.return_value = "2.0.1"
    client.latest_version_of.return_value = "0.0"
    client.id_of.return_value = None
    return p, client


async def test_diagnostics_redacts_password_and_returns_data(hass, request):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={
            "ip_address": "1.2.3.4",
            "port": 80,
            "password": "supersecret",
            "name": "Atrea",
        },
    )
    entry.add_to_hass(hass)
    p, _ = _patched_client()
    request.addfinalizer(p.stop)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        AsyncMock(return_value=True),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert "entry" in result
    assert "data" in result
    # password redacted
    assert result["entry"]["data"]["password"] == "**REDACTED**"
    assert result["entry"]["data"]["ip_address"] == "1.2.3.4"
    # data payload populated from the coordinator
    assert result["data"]["registers"]["I10211"] == "215"
    assert result["data"]["version"] == "2.0.1"
    assert result["data"]["supported_modes"] == {"VENTILATION": True}
    assert result["data"]["forced_modes"] == {1: "IN1"}
