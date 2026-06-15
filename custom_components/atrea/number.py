"""Number platform for Atrea HRU units (target supply temperature)."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.const import CONF_IP_ADDRESS, CONF_NAME, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AtreaConfigEntry
from . import derive
from .coordinator import AtreaDataUpdateCoordinator
from .entity import AtreaEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AtreaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Atrea number platform from a config entry."""
    coordinator: AtreaDataUpdateCoordinator = entry.runtime_data.coordinator

    opts = {**entry.data, **entry.options}
    name = opts.get(CONF_NAME) or "atrea"
    ip = str(opts[CONF_IP_ADDRESS])

    async_add_entities([AtreaTargetTemperature(coordinator, entry.entry_id, name, ip)])


class AtreaTargetTemperature(AtreaEntity, NumberEntity):
    """Target supply temperature setpoint for the Atrea unit."""

    _attr_translation_key = "target_temperature"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_min_value = 10
    _attr_native_max_value = 40
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: AtreaDataUpdateCoordinator,
        entry_id: str,
        name: str,
        ip: str,
    ) -> None:
        super().__init__(coordinator, entry_id, name, ip)
        self._attr_unique_id = f"{self._device_slug}_target_temperature"

    @property
    def native_value(self) -> float | None:
        status = self.coordinator.data.status if self.coordinator.data else None
        return derive.temp(status, "H10706")

    async def async_set_native_value(self, value: float) -> None:
        b = self._builder()
        b.set_temperature(value)
        await self._commit(b)
