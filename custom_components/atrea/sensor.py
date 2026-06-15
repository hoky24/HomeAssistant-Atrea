"""Render-only Home Assistant sensor platform for Atrea HRU units.

Each sensor is described by a frozen ``AtreaSensorEntityDescription`` carrying
a pure ``value_fn`` that derives its value from the coordinator's
``AtreaStatus`` (or ``None`` when no status is available yet). All state is
computed by the helpers in ``derive``; this module performs NO I/O.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_NAME,
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pyatrea import AtreaStatus

from . import AtreaConfigEntry
from . import derive
from .coordinator import AtreaDataUpdateCoordinator
from .entity import AtreaEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class AtreaSensorEntityDescription(SensorEntityDescription):
    """Describe an Atrea sensor with a pure value derivation function."""

    value_fn: Callable[[AtreaStatus | None], float | int | None]


SENSORS: tuple[AtreaSensorEntityDescription, ...] = (
    AtreaSensorEntityDescription(
        key="outside_temp",
        value_fn=lambda st: derive.temp(st, "I10211"),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    AtreaSensorEntityDescription(
        key="inside_temp",
        value_fn=lambda st: derive.temp(st, "I10215"),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    AtreaSensorEntityDescription(
        key="supply_temp",
        value_fn=lambda st: derive.temp(st, "I10212"),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    AtreaSensorEntityDescription(
        key="extract_temp",
        value_fn=lambda st: derive.temp(st, "I10213"),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    AtreaSensorEntityDescription(
        key="exhaust_temp",
        value_fn=lambda st: derive.temp(st, "I10214"),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    AtreaSensorEntityDescription(
        key="avg_outside_temp",
        value_fn=lambda st: derive.temp(st, "I11420"),
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    AtreaSensorEntityDescription(
        key="efficiency",
        value_fn=derive.efficiency,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    AtreaSensorEntityDescription(
        key="fan_drive_m1",
        value_fn=lambda st: derive.fan_drive(st, "H10200"),
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    AtreaSensorEntityDescription(
        key="fan_drive_m2",
        value_fn=lambda st: derive.fan_drive(st, "H10201"),
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    AtreaSensorEntityDescription(
        key="fan_hours_m1",
        value_fn=lambda st: derive.fan_hours(st, "H13500", "H13501"),
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
    ),
    AtreaSensorEntityDescription(
        key="fan_hours_m2",
        value_fn=lambda st: derive.fan_hours(st, "H13502", "H13503"),
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.HOURS,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AtreaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Atrea sensor platform from a config entry."""
    coordinator: AtreaDataUpdateCoordinator = entry.runtime_data.coordinator

    # Options override data (consistent with the climate/update platforms).
    opts = {**entry.data, **entry.options}
    name = opts.get(CONF_NAME) or "atrea"
    ip = str(opts[CONF_IP_ADDRESS])

    async_add_entities(
        [
            AtreaSensor(coordinator, entry.entry_id, name, ip, description)
            for description in SENSORS
        ]
    )


class AtreaSensor(AtreaEntity, SensorEntity):
    """Render-only sensor entity deriving its value from the coordinator."""

    entity_description: AtreaSensorEntityDescription

    def __init__(
        self,
        coordinator: AtreaDataUpdateCoordinator,
        entry_id: str,
        name: str,
        ip: str,
        description: AtreaSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_id, name, ip)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_unique_id = f"{self._device_slug}_{description.key}"

    @property
    def native_value(self) -> float | int | None:
        status = self.coordinator.data.status if self.coordinator.data else None
        return self.entity_description.value_fn(status)
