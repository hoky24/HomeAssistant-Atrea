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

from .coordinator import AtreaDataUpdateCoordinator
from .entity import AtreaEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: Callable
) -> None:
    """Set up the Atrea update platform from a config entry."""
    coordinator: AtreaDataUpdateCoordinator = entry.runtime_data.coordinator

    # Options override data (consistent with the climate platform).
    opts = {**entry.data, **entry.options}
    name = opts.get(CONF_NAME) or "atrea"
    ip = str(opts[CONF_IP_ADDRESS])

    async_add_entities([AtreaUpdate(coordinator, entry.entry_id, name, ip)])


class AtreaUpdate(AtreaEntity, UpdateEntity):
    """Render-only update entity deriving firmware state from the coordinator."""

    def __init__(
        self,
        coordinator: AtreaDataUpdateCoordinator,
        entry_id: str,
        name: str,
        ip: str,
    ) -> None:
        super().__init__(coordinator, entry_id, name, ip)
        self._attr_unique_id = f"{self._device_slug}_update"
        self._attr_name = f"{name} firmware"

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
            return UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
        return UpdateEntityFeature(0)

    @property
    def in_progress(self) -> bool:
        # Legacy reported flash progress via I10005 > 3.
        status = self.coordinator.data.status if self.coordinator.data else None
        if status is None:
            return False
        raw = status.registers.get("I10005")
        return raw is not None and int(raw) > 3

    # -- write path -----------------------------------------------------------

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Queue the firmware-update command and refresh the coordinator."""
        builder = self._builder()
        builder.prepare_update()
        # A firmware install can change model/labels; drop the firmware-static
        # cache so the post-commit refresh reloads it instead of staying stale.
        self.coordinator.invalidate_static()
        await self._commit(builder)
