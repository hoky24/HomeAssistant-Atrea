from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from . import AtreaConfigEntry

TO_REDACT = {CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AtreaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "data": {
            "registers": data.status.registers if data and data.status else {},
            "model": data.model if data else None,
            "version": data.version if data else None,
            "latest_version": data.latest_version if data else None,
            "unit_id": data.unit_id if data else None,
            "supported_modes": {
                m.name: v
                for m, v in (data.supported_modes if data else {}).items()
            },
            "forced_modes": {
                i: m.name
                for i, m in (data.forced_modes if data else {}).items()
            },
        },
    }
