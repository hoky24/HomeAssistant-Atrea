"""Switch platform for Atrea HRU units (night precooling)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import CONF_IP_ADDRESS, CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AtreaConfigEntry
from .coordinator import AtreaDataUpdateCoordinator
from .entity import AtreaEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AtreaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Atrea switch platform from a config entry."""
    coordinator: AtreaDataUpdateCoordinator = entry.runtime_data.coordinator

    opts = {**entry.data, **entry.options}
    name = opts.get(CONF_NAME) or "atrea"
    ip = str(opts[CONF_IP_ADDRESS])

    async_add_entities([AtreaNightPrecooling(coordinator, entry.entry_id, name, ip)])


class AtreaNightPrecooling(AtreaEntity, SwitchEntity):
    """Automatic night-precooling config coil (C10902) for the Atrea unit.

    This is a COMMISSIONING-menu config flag ("enable automatic night
    precooling"), not the runtime night-precooling regime. It is only editable
    while the unit reports register ``H11022 == 0``; otherwise it is gated
    unavailable.
    """

    _attr_translation_key = "night_precooling"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AtreaDataUpdateCoordinator,
        entry_id: str,
        name: str,
        ip: str,
    ) -> None:
        super().__init__(coordinator, entry_id, name, ip)
        self._attr_unique_id = f"{self._device_slug}_night_precooling"

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        if not super().available or data is None or data.status is None:
            return False
        return data.status.registers.get("H11022", "0") == "0"

    @property
    def is_on(self) -> bool:
        return (
            self.coordinator.data.status.registers.get("C10902") == "1"
            if self.coordinator.data and self.coordinator.data.status
            else False
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        b = self._builder()
        b.commands["C10902"] = f"{1:05}"
        await self._commit(b)

    async def async_turn_off(self, **kwargs: Any) -> None:
        b = self._builder()
        b.commands["C10902"] = f"{0:05}"
        await self._commit(b)
