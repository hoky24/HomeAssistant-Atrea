"""Render-only Home Assistant binary sensor platform for Atrea HRU units.

Each binary sensor is described by a frozen
``AtreaBinarySensorEntityDescription`` carrying a pure, None-safe ``is_on_fn``
that derives its boolean state from the coordinator's ``AtreaStatus`` (or
``None`` when no status is available yet), plus an optional ``attrs_fn`` for
extra state attributes derived from the full ``AtreaData``. All state is
computed by ``derive`` and ``pyatrea.registers.by_role``; this module performs
NO I/O.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import CONF_IP_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pyatrea import AtreaStatus
from pyatrea.registers import by_role

from . import AtreaConfigEntry
from . import derive
from .coordinator import AtreaDataUpdateCoordinator
from .entity import AtreaEntity
from .models import AtreaData

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class AtreaBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe an Atrea binary sensor with pure derivation functions."""

    is_on_fn: Callable[[AtreaStatus | None], bool]
    attrs_fn: Callable[[AtreaData], dict[str, Any]] | None = None


_WARNING_IDS = by_role("warning")
_ALERT_IDS = by_role("alert")
_DEFROST_IDS = ("D11117", "D11118", "D11149")


def _reg_on(status: AtreaStatus | None, key: str) -> bool:
    return status is not None and status.registers.get(key) == "1"


def _any_reg_on(status: AtreaStatus | None, keys: list[str] | tuple[str, ...]) -> bool:
    return status is not None and any(status.registers.get(r) == "1" for r in keys)


BINARY_SENSORS: tuple[AtreaBinarySensorEntityDescription, ...] = (
    AtreaBinarySensorEntityDescription(
        key="filter",
        is_on_fn=lambda st: _reg_on(st, "D11183"),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    AtreaBinarySensorEntityDescription(
        key="any_warning",
        is_on_fn=lambda st: _any_reg_on(st, _WARNING_IDS),
        device_class=BinarySensorDeviceClass.PROBLEM,
        attrs_fn=lambda data: {
            "active": derive.active_flags(data.status, _WARNING_IDS, data.translations)
        },
    ),
    AtreaBinarySensorEntityDescription(
        key="any_alert",
        is_on_fn=lambda st: _any_reg_on(st, _ALERT_IDS),
        device_class=BinarySensorDeviceClass.PROBLEM,
        attrs_fn=lambda data: {
            "active": derive.active_flags(data.status, _ALERT_IDS, data.translations)
        },
    ),
    AtreaBinarySensorEntityDescription(
        key="heating",
        is_on_fn=lambda st: _reg_on(st, "C10215"),
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    AtreaBinarySensorEntityDescription(
        key="cooling",
        is_on_fn=lambda st: _reg_on(st, "C10216"),
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    AtreaBinarySensorEntityDescription(
        key="defrost",
        is_on_fn=lambda st: _any_reg_on(st, _DEFROST_IDS),
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AtreaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Atrea binary sensor platform from a config entry."""
    coordinator: AtreaDataUpdateCoordinator = entry.runtime_data.coordinator

    # Options override data (consistent with the climate/sensor platforms).
    opts = {**entry.data, **entry.options}
    name = opts.get(CONF_NAME) or "atrea"
    ip = str(opts[CONF_IP_ADDRESS])

    async_add_entities(
        [
            AtreaBinarySensor(coordinator, entry.entry_id, name, ip, description)
            for description in BINARY_SENSORS
        ]
    )


class AtreaBinarySensor(AtreaEntity, BinarySensorEntity):
    """Render-only binary sensor entity deriving its state from the coordinator."""

    entity_description: AtreaBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: AtreaDataUpdateCoordinator,
        entry_id: str,
        name: str,
        ip: str,
        description: AtreaBinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_id, name, ip)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_unique_id = f"{self._device_slug}_{description.key}"

    @property
    def is_on(self) -> bool:
        status = self.coordinator.data.status if self.coordinator.data else None
        return self.entity_description.is_on_fn(status)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        description = self.entity_description
        if description.attrs_fn and self.coordinator.data:
            return description.attrs_fn(self.coordinator.data)
        return None
