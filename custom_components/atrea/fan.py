"""Home Assistant fan platform for Atrea HRU units (primary control).

The fan entity is the PRIMARY user-facing control surface for the unit's
ventilation: a percentage speed (power) plus a preset-mode selector derived
from the unit's supported Atrea modes. State is derived purely from the
coordinator; writes are staged onto a ``CommandBuilder`` and pushed through
the shared ``AtreaEntity`` commit plumbing.

Register asymmetry (proven, HW-verified): ``H10704`` is the power READBACK
register read via ``status.value``; ``set_power`` targets the WRITE register
``H10708``. Do not "reconcile" them.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.const import CONF_IP_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pyatrea import AtreaMode

from . import AtreaConfigEntry
from .coordinator import AtreaDataUpdateCoordinator
from .entity import AtreaEntity

PARALLEL_UPDATES = 1

_MIN_PCT = 12
_MAX_PCT = 100


def _display_name(mode: AtreaMode) -> str:
    """Render an ``AtreaMode`` as a human-readable preset label.

    VENTILATION -> "Ventilation", AUTOMATIC -> "Automatic",
    CIRCULATION_AND_VENTILATION -> "Circulation And Ventilation".
    """
    return mode.name.replace("_", " ").title()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AtreaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Atrea fan platform from a config entry."""
    coordinator: AtreaDataUpdateCoordinator = entry.runtime_data.coordinator

    opts = {**entry.data, **entry.options}
    name = opts.get(CONF_NAME) or "atrea"
    ip = str(opts[CONF_IP_ADDRESS])

    async_add_entities([AtreaFan(coordinator, entry.entry_id, name, ip)])


class AtreaFan(AtreaEntity, FanEntity):
    """Primary fan control: percentage speed + preset modes."""

    _attr_translation_key = "fan"
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    # Per-1% granularity across the 12..100 operating range (89 steps).
    _attr_speed_count = 89

    def __init__(
        self,
        coordinator: AtreaDataUpdateCoordinator,
        entry_id: str,
        name: str,
        ip: str,
    ) -> None:
        super().__init__(coordinator, entry_id, name, ip)
        self._attr_unique_id = f"{self._device_slug}_fan"

    # -- state ----------------------------------------------------------------

    @property
    def percentage(self) -> int | None:
        """Current fan power, read from the H10704 readback register."""
        status = self.coordinator.data.status if self.coordinator.data else None
        if status is None:
            return None
        value = status.value("H10704")
        if value is None:
            return None
        return max(0, min(100, int(value)))

    @property
    def preset_modes(self) -> list[str]:
        """Preset labels derived from the unit's supported modes."""
        data = self.coordinator.data
        if data is None:
            return []
        return [
            _display_name(mode)
            for mode, supported in data.supported_modes.items()
            if supported
        ]

    @property
    def preset_mode(self) -> str | None:
        """Current preset label from the coordinator's resolved mode."""
        data = self.coordinator.data
        if data is None or data.status is None:
            return None
        mode = self.coordinator.client.mode_of(data.status)
        if mode is None:
            return None
        return _display_name(mode)

    @property
    def is_on(self) -> bool:
        return (self.percentage or 0) > 0

    # -- write handlers -------------------------------------------------------

    async def async_set_percentage(self, percentage: int) -> None:
        """Set fan power; <= 0 turns the unit off."""
        if percentage <= 0:
            await self.async_turn_off()
            return
        pct = max(_MIN_PCT, min(_MAX_PCT, percentage))
        builder = self._builder()
        builder.set_power(pct)
        await self._commit(builder)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the ventilation mode from a preset label."""
        mode = next(
            (m for m in AtreaMode if _display_name(m) == preset_mode),
            None,
        )
        if mode is None:
            raise ValueError(f"Unknown preset mode: {preset_mode}")
        builder = self._builder()
        builder.set_mode(mode)
        await self._commit(builder)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn the unit on via preset, percentage, or a sensible default."""
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        elif percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self.async_set_percentage(_MIN_PCT)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the unit off (replicates v2 climate.py off path).

        Replicated v2 climate.async_turn_off line: ``builder.set_mode(AtreaMode.OFF)``.
        """
        builder = self._builder()
        builder.set_mode(AtreaMode.OFF)
        await self._commit(builder)
