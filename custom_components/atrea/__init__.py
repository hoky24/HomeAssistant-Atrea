import asyncio

from homeassistant.const import (
    CONF_IP_ADDRESS,
    CONF_PORT,
    CONF_PASSWORD,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryNotReady
from pyatrea import Atrea

from .utils import update_listener
from .const import DOMAIN, LOGGER, MIN_TIME_BETWEEN_SCANS


async def async_migrate_entry(hass, config_entry: ConfigEntry):
    """Migrate old entry."""
    LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        new = {**config_entry.data}
        new[CONF_PORT] = 80
        # async_update_entry handles both data and version; ConfigEntry.data /
        # .version are read-only in modern HA so they must not be assigned
        # directly. Previously 'new' was also referenced outside this branch,
        # raising NameError for any version != 1.
        hass.config_entries.async_update_entry(config_entry, data=new, version=2)
        LOGGER.info("Migration to version 2 successful")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await hass.config_entries.async_unload_platforms(entry, ["climate", "update"])
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    async def async_update_data():
        # Wrap runtime polling I/O: a network blip after a successful setup
        # (same Errno 101 race the setup path guards) must surface as
        # UpdateFailed so the coordinator marks entities unavailable and retries
        # cleanly, instead of leaking a raw exception (traceback spam) and
        # leaving hass.data partially updated.
        try:
            data = hass.data[DOMAIN][entry.entry_id]
            data["status"] = await hass.async_add_executor_job(atrea.getStatus, False)
            data["params"] = await hass.async_add_executor_job(atrea.getParams, False)
            data["supportedModes"] = (
                await hass.async_add_executor_job(atrea.getSupportedModes)
            ).items()
            data["userLabels"] = await hass.async_add_executor_job(atrea.loadUserLabels)
            data["supportedForcedModes"] = (
                await hass.async_add_executor_job(atrea.getSupportedForcedModes)
            ).items()
        except (OSError, asyncio.TimeoutError, ConnectionError) as e:
            raise UpdateFailed(f"Atrea update failed: {e}") from e

    atreaCoordinator = DataUpdateCoordinator(
        hass,
        LOGGER,
        name="Atrea resource status",
        update_method=async_update_data,
        update_interval=MIN_TIME_BETWEEN_SCANS,
    )

    atrea = Atrea(
        entry.data.get(CONF_IP_ADDRESS),
        entry.data.get(CONF_PORT),
        entry.data.get(CONF_PASSWORD),
    )

    # Network resilience: if the first poll fails because the network isn't
    # ready (e.g., supervisor cold boot before DHCP/DNS settle — observed
    # 2026-06-08 with Errno 101 Network unreachable), raise ConfigEntryNotReady
    # so HA's config_entries machinery retries with exponential backoff
    # instead of leaving the entity unavailable for hours.
    try:
        status = await hass.async_add_executor_job(atrea.getStatus, False)
    except (OSError, asyncio.TimeoutError, ConnectionError) as e:
        LOGGER.warning("Atrea unreachable during setup (%s); HA will retry", e)
        raise ConfigEntryNotReady(f"Atrea unreachable: {e}") from e

    if not status:
        raise ConfigEntryNotReady("Incorrect password or too many signed in users.")
    else:
        # setdefault, not '= {}': a second Atrea config entry must not wipe the
        # first entry's data on setup.
        hass.data.setdefault(DOMAIN, {})

        # Same protection for the remaining one-shot setup calls — any of them
        # can hit the same network race during boot.
        try:
            hass.data[DOMAIN][entry.entry_id] = {
                "atrea": atrea,
                "update_listener": entry.add_update_listener(update_listener),
                "coordinator": atreaCoordinator,
                "supportedModes": (
                    await hass.async_add_executor_job(atrea.getSupportedModes)
                ).items(),
                "userLabels": (await hass.async_add_executor_job(atrea.loadUserLabels)),
                "supportedForcedModes": (
                    await hass.async_add_executor_job(atrea.getSupportedForcedModes)
                ).items(),
                "status": status,
                "model": (await hass.async_add_executor_job(atrea.getModel)),
                "params": (await hass.async_add_executor_job(atrea.getParams, False)),
                "translations": (await hass.async_add_executor_job(atrea.getTranslations)),
                "configDir": (await hass.async_add_executor_job(atrea.getConfigDir)),
            }
        except (OSError, asyncio.TimeoutError, ConnectionError) as e:
            LOGGER.warning("Atrea unreachable during mid-setup (%s); HA will retry", e)
            raise ConfigEntryNotReady(f"Atrea mid-setup error: {e}") from e

        entry.async_on_unload(hass.data[DOMAIN][entry.entry_id]["update_listener"])

        await hass.async_create_task(
            hass.config_entries.async_forward_entry_setups(entry, ["climate", "update"])
        )
        return True
