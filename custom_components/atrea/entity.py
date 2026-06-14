"""Shared base entity for Atrea HRU platforms.

Both the climate and update entities derive their identity, device info, and
write plumbing from the same coordinator data. This base centralises the
duplicated ``__init__`` field storage, the ``slugify`` device slug, the
``device_info`` block (so both entities group under one device), the
``CommandBuilder`` seeding (``_builder``), and the commit+refresh+error-wrap
(``_commit``).
"""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify
from pyatrea import AtreaConnectionError, AtreaParams, CommandBuilder

from .const import DOMAIN
from .coordinator import AtreaDataUpdateCoordinator


class AtreaEntity(CoordinatorEntity[AtreaDataUpdateCoordinator]):
    """Common identity/device/write plumbing for Atrea entities."""

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

    # -- identity / device ----------------------------------------------------

    @property
    def _device_slug(self) -> str:
        return slugify(f"atrea_{self.ip}")

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
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_slug)},
            name=self._name,
            manufacturer=self.brand,
            model=self.model,
            sw_version=data.version if data else None,
            hw_version=data.unit_id if data else None,
            connections=set(),
        )

    # -- write helpers --------------------------------------------------------

    def _builder(self) -> CommandBuilder:
        """Build a CommandBuilder seeded from current coordinator data."""
        data = self.coordinator.data
        regs = set(data.status.registers) if data and data.status else set()
        params = data.status.params if data and data.status else AtreaParams()
        return self.coordinator.client.command_builder(
            params,
            regs,
            modes_to_ids=data.modes_to_ids if data else {},
            supported_modes=data.supported_modes if data else {},
        )

    async def _commit(self, builder: CommandBuilder) -> None:
        """Commit the builder and refresh the coordinator.

        Transport failures (``AtreaConnectionError``) are surfaced to HA as
        ``HomeAssistantError`` so the service call reports a clean failure.
        """
        try:
            await self.coordinator.client.commit(builder)
        except AtreaConnectionError as err:
            raise HomeAssistantError(f"Atrea write failed: {err}") from err
        await self.coordinator.async_request_refresh()
