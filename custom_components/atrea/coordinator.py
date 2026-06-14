from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pyatrea import AtreaClient
from pyatrea.exceptions import AtreaAuthError, AtreaConnectionError, AtreaResponseError

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

    async def _async_update_data(self) -> AtreaData:
        try:
            status = await self.client.fetch_status(with_params=True)
            supported, ids_to_modes, modes_to_ids, forced = (
                await self.client.fetch_supported(status)
            )
            if not self._static_loaded:
                self._config_dir = await self.client.fetch_config_dir()
                self._translations = await self.client.fetch_translations()
                self._user_labels = await self.client.fetch_user_labels()
                self._static_loaded = True
        except AtreaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (AtreaConnectionError, AtreaResponseError) as err:
            raise UpdateFailed(str(err)) from err

        return AtreaData(
            status=status,
            supported_modes=supported,
            ids_to_modes=ids_to_modes,
            modes_to_ids=modes_to_ids,
            forced_modes=forced,
            user_labels=self._user_labels,
            translations=self._translations,
            model=self.client.model_of(status, self._config_dir),
            version=self.client.version_of(status),
            latest_version=self.client.latest_version_of(status),
            unit_id=self.client.id_of(status),
            config_dir=self._config_dir,
        )
