from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pyatrea import AtreaClient, AtreaStatus, Descriptors
from pyatrea.exceptions import AtreaAuthError, AtreaConnectionError, AtreaResponseError

from .const import DOMAIN, LOGGER, MIN_TIME_BETWEEN_SCANS
from .models import AtreaData

# Consecutive failed polls before a "unit unreachable" repair issue is raised.
UNREACHABLE_THRESHOLD = 5


class AtreaDataUpdateCoordinator(DataUpdateCoordinator[AtreaData]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: AtreaClient,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=MIN_TIME_BETWEEN_SCANS,
            config_entry=config_entry,
        )
        self.client = client
        self._static_loaded = False
        # Firmware-static descriptors (config_dir, translations, user_labels,
        # mode maps), fetched once and cached.
        self._descriptors: Descriptors = Descriptors()
        # Repair-issue bookkeeping for prolonged unreachability.
        self._consecutive_failures = 0
        self._unreachable_issue_active = False

    @property
    def _entry_id(self) -> str:
        entry = self.config_entry
        return entry.entry_id if entry is not None else "unknown"

    @property
    def _unit_name(self) -> str:
        entry = self.config_entry
        if entry is not None and entry.title:
            return entry.title
        return "Atrea"

    def _raise_unreachable_issue(self) -> None:
        """Surface prolonged unreachability as an actionable repair issue."""
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"unreachable_{self._entry_id}",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="unit_unreachable",
            translation_placeholders={"name": self._unit_name},
        )
        self._unreachable_issue_active = True

    def _clear_unreachable_issue(self) -> None:
        """Clear a previously-raised unreachability repair issue, if any."""
        if self._unreachable_issue_active:
            ir.async_delete_issue(
                self.hass, DOMAIN, f"unreachable_{self._entry_id}"
            )
            self._unreachable_issue_active = False

    def invalidate_static(self) -> None:
        """Force a re-fetch of firmware-static data on the next refresh
        (e.g. after a firmware install changed model/labels)."""
        self._static_loaded = False

    async def _async_update_data(self) -> AtreaData:
        try:
            status = await self.client.fetch_status()
            # Retain last-good registers: a partial poll must not zero attributes
            # the orchestrator reads (legacy kept last-known per-attribute).
            if self.data is not None and self.data.status is not None:
                merged = {**self.data.status.registers, **status.registers}
                status = AtreaStatus(registers=merged, params=status.params)
            if not self._static_loaded:
                self._descriptors = await self.client.fetch_descriptors()
                self._static_loaded = True
        except AtreaAuthError as err:
            # Auth failures are repaired via the reauth flow (ConfigEntryAuthFailed),
            # not via a repair issue, so the unreachable counter is untouched.
            raise ConfigEntryAuthFailed(str(err)) from err
        except (AtreaConnectionError, AtreaResponseError) as err:
            self._consecutive_failures += 1
            if self._consecutive_failures >= UNREACHABLE_THRESHOLD:
                self._raise_unreachable_issue()
            raise UpdateFailed(str(err)) from err

        # Successful poll: reset the failure streak and clear any active issue.
        self._consecutive_failures = 0
        self._clear_unreachable_issue()

        # Recompute the writable/mode maps each cycle from the current status
        # overlaid on the cached static descriptors (pure, no I/O).
        supported, ids_to_modes, modes_to_ids, forced = AtreaClient.supported_from(
            status, self._descriptors
        )

        return AtreaData(
            status=status,
            supported_modes=supported,
            ids_to_modes=ids_to_modes,
            modes_to_ids=modes_to_ids,
            forced_modes=forced,
            user_labels=self._descriptors.user_labels,
            translations=self._descriptors.translations,
            model=self.client.model_of(status, self._descriptors.config_dir),
            version=self.client.version_of(status),
            latest_version=self.client.latest_version_of(status),
            unit_id=self.client.id_of(status),
            config_dir=self._descriptors.config_dir,
        )
