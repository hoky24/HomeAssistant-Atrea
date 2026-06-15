from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from pyatrea import AtreaClient, HttpTransport, ModbusTransport

from .const import CONF_SLAVE_ID, CONF_TRANSPORT, DOMAIN, PLATFORMS, TRANSPORT_MODBUS
from .coordinator import AtreaDataUpdateCoordinator
from .models import AtreaRuntimeData
from .services import SERVICE_APPLY, async_setup_services, async_unload_services

type AtreaConfigEntry = ConfigEntry[AtreaRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: AtreaConfigEntry) -> bool:
    transport_kind = entry.data.get(CONF_TRANSPORT, "http")
    transport: HttpTransport | ModbusTransport
    if transport_kind == TRANSPORT_MODBUS:
        transport = ModbusTransport(
            entry.data[CONF_IP_ADDRESS],
            entry.data.get(CONF_PORT, 502),
            entry.data.get(CONF_SLAVE_ID, 1),
        )
    else:
        transport = HttpTransport(
            entry.data[CONF_IP_ADDRESS],
            entry.data.get(CONF_PORT, 80),
            entry.data.get(CONF_PASSWORD, ""),
            async_get_clientsession(hass),
        )
    client = AtreaClient(transport)
    coordinator = AtreaDataUpdateCoordinator(hass, client, config_entry=entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = AtreaRuntimeData(
        client=client, coordinator=coordinator, transport=transport
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if not hass.services.has_service(DOMAIN, SERVICE_APPLY):
        async_setup_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AtreaConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and entry.runtime_data is not None:
        await entry.runtime_data.transport.close()
        remaining = [
            e
            for e in hass.config_entries.async_loaded_entries(DOMAIN)
            if e.entry_id != entry.entry_id
        ]
        if not remaining and hass.services.has_service(DOMAIN, SERVICE_APPLY):
            async_unload_services(hass)
    return unloaded


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version == 1:
        data = {**entry.data, CONF_PORT: 80}
        hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True
