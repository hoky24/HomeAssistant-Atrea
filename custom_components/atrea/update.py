"""Render-only Home Assistant update entity for Atrea HRU units.

Derives state from the data coordinator (``coordinator.data``) as pure
computation. The single write path is ``async_install`` which queues the
firmware-update command via the client's ``CommandBuilder`` and commits it.

The entity shares the SAME device identifiers as the climate entity
(``slugify(f"atrea_{ip}")``) so both appear under one device, while using a
distinct ``unique_id`` suffixed with ``_update``.
"""

from __future__ import annotations

from typing import Any, Callable

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify
from pyatrea import AtreaConnectionError, AtreaParams

from .const import DOMAIN
from .coordinator import AtreaDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: Callable
) -> None:
    """Set up the Atrea update platform from a config entry."""
    coordinator: AtreaDataUpdateCoordinator = entry.runtime_data.coordinator

    name = entry.data.get(CONF_NAME) or "atrea"
    ip = str(entry.data[CONF_IP_ADDRESS])

    async_add_entities([AtreaUpdate(coordinator, entry.entry_id, name, ip)])


class AtreaUpdate(CoordinatorEntity[AtreaDataUpdateCoordinator], UpdateEntity):
    """Render-only update entity deriving firmware state from the coordinator."""

    def __init__(
        self,
        coordinator: AtreaDataUpdateCoordinator,
        entry_id: str,
        name: str,
        ip: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._name = name
        self.ip = ip
        self._attr_unique_id = slugify(f"atrea_{ip}_update")
        self._attr_name = f"{name} firmware"

    # -- identity / device ----------------------------------------------------

    @property
    def brand(self) -> str:
        return "ATREA s.r.o."

    @property
    def model(self) -> str | None:
        model = self.coordinator.data.model if self.coordinator.data else None
        if model:
            return f"{model.get('category', '')} {model.get('model', '')}".strip()
        return None

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data
        # Identifiers MUST match the climate entity (slugify(f"atrea_{ip}"))
        # so both entities are grouped under a single device.
        return DeviceInfo(
            identifiers={(DOMAIN, slugify(f"atrea_{self.ip}"))},
            name=self._name,
            manufacturer=self.brand,
            model=self.model,
            sw_version=data.version if data else None,
            hw_version=data.unit_id if data else None,
            connections=set(),
        )

    # -- derived state --------------------------------------------------------

    @property
    def installed_version(self) -> str | None:
        return self.coordinator.data.version if self.coordinator.data else None

    @property
    def latest_version(self) -> str | None:
        data = self.coordinator.data
        if data is None:
            return None
        latest = data.latest_version
        # "0.0" (and None) means the unit reports no real latest; advertising it
        # would look like a downgrade, so fall back to the installed version.
        if latest in (None, "0.0"):
            return data.version
        return latest

    @property
    def supported_features(self) -> UpdateEntityFeature:
        # Only offer INSTALL when a real, differing latest version is known.
        if (
            self.latest_version is not None
            and self.latest_version != self.installed_version
        ):
            return UpdateEntityFeature.INSTALL
        return UpdateEntityFeature(0)

    # -- write path -----------------------------------------------------------

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Queue the firmware-update command and refresh the coordinator."""
        data = self.coordinator.data
        regs = set(data.status.registers) if data and data.status else set()
        params = data.status.params if data and data.status else AtreaParams()
        builder = self.coordinator.client.command_builder(
            params,
            regs,
            modes_to_ids=data.modes_to_ids if data else {},
            supported_modes=data.supported_modes if data else {},
        )
        builder.prepare_update()
        try:
            await self.coordinator.client.commit(builder)
        except AtreaConnectionError as err:
            raise HomeAssistantError(f"Atrea update failed: {err}") from err
        await self.coordinator.async_request_refresh()
