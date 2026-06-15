from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pyatrea import AtreaMode, AtreaStatus, Descriptors

from custom_components.atrea.const import DOMAIN
from custom_components.atrea.diagnostics import (
    async_get_config_entry_diagnostics,
)

# supported_from output the diagnostics payload reflects.
_SUPPORTED = ({AtreaMode.VENTILATION: True}, {}, {}, {1: AtreaMode.IN1})


def _patched_client():
    patchers = [
        patch("custom_components.atrea.AtreaClient"),
        patch("custom_components.atrea.HttpTransport"),
        patch("custom_components.atrea.ModbusTransport"),
    ]
    cls = patchers[0].start()
    patchers[1].start()
    patchers[2].start()
    client = cls.return_value
    client.fetch_status = AsyncMock(
        return_value=AtreaStatus(registers={"H10700": "0", "I10211": "215"})
    )
    client.fetch_descriptors = AsyncMock(
        return_value=Descriptors(
            user_labels={}, translations={"params": {}, "words": {}}
        )
    )
    client.model_of.return_value = None
    client.version_of.return_value = "2.0.1"
    client.latest_version_of.return_value = "0.0"
    client.id_of.return_value = None

    def _stop():
        for p in patchers:
            p.stop()

    return _stop, client


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
    stop, _ = _patched_client()
    request.addfinalizer(stop)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        AsyncMock(return_value=True),
    ), patch(
        "custom_components.atrea.coordinator.AtreaClient.supported_from",
        return_value=_SUPPORTED,
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
