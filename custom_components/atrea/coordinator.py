from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pyatrea import AtreaClient, AtreaStatus
from pyatrea.exceptions import AtreaAuthError, AtreaConnectionError, AtreaResponseError
from pyatrea.parser import supported_modes_from_status

from .const import DOMAIN, LOGGER, MIN_TIME_BETWEEN_SCANS
from .models import AtreaData


class AtreaDataUpdateCoordinator(DataUpdateCoordinator[AtreaData]):
    def __init__(self, hass: HomeAssistant, client: AtreaClient, config_entry=None) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=MIN_TIME_BETWEEN_SCANS,
            config_entry=config_entry,
        )
        self.client = client
        self._static_loaded = False
        self._config_dir = None
        self._translations: dict[str, dict] = {"params": {}, "words": {}}
        self._user_labels: dict[str, str] = {}
        # Firmware-static userctrl data, fetched once and cached.
        self._ec_writable: dict = {}
        self._ids_to_modes: dict = {}
        self._modes_to_ids: dict = {}
        self._forced_modes: dict = {}

    async def _async_update_data(self) -> AtreaData:
        try:
            status = await self.client.fetch_status(with_params=True)
            # Retain last-good registers: a partial poll must not zero attributes
            # the orchestrator reads (legacy kept last-known per-attribute).
            if self.data is not None and self.data.status is not None:
                merged = {**self.data.status.registers, **status.registers}
                status = AtreaStatus(registers=merged, params=status.params)
            if not self._static_loaded:
                (
                    self._ec_writable,
                    self._ids_to_modes,
                    self._modes_to_ids,
                    self._forced_modes,
                ) = await self.client.fetch_userctrl()
                self._config_dir = await self.client.fetch_config_dir()
                self._translations = await self.client.fetch_translations()
                self._user_labels = await self.client.fetch_user_labels()
                self._static_loaded = True
        except AtreaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (AtreaConnectionError, AtreaResponseError) as err:
            raise UpdateFailed(str(err)) from err

        # Recompute only the dynamic I12004 writable bitmask each cycle; fall
        # back to the cached static userctrl ModeEC when the bitmask is absent.
        bitmask = supported_modes_from_status(status)
        supported = bitmask if bitmask is not None else self._ec_writable

        return AtreaData(
            status=status,
            supported_modes=supported,
            ids_to_modes=self._ids_to_modes,
            modes_to_ids=self._modes_to_ids,
            forced_modes=self._forced_modes,
            user_labels=self._user_labels,
            translations=self._translations,
            model=self.client.model_of(status, self._config_dir),
            version=self.client.version_of(status),
            latest_version=self.client.latest_version_of(status),
            unit_id=self.client.id_of(status),
            config_dir=self._config_dir,
        )
