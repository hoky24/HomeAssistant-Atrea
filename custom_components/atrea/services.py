"""Atrea ``atrea.apply`` service.

A single atomic write of program + operating mode + power + target supply
temperature. The orchestrator needs these to land in one commit so the unit's
state machine reads a consistent program: writing them separately lets the unit
read a stale program mid-sequence and jump to TEMPORARY.

The service resolves a standard HA target (``entity_id`` / ``device_id``) to the
owning config entries, and for each entry's coordinator builds ONE
``CommandBuilder``, stages only the provided fields, then commits once and
refreshes. The deprecated climate entity used to bundle this via
``set_hvac_mode``; this service replaces that bundling cleanly.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pyatrea import AtreaConnectionError, AtreaMode, AtreaProgram

from .const import DOMAIN
from .coordinator import AtreaDataUpdateCoordinator
from .derive import mode_display_name

SERVICE_APPLY = "apply"

ATTR_PROGRAM = "program"
ATTR_MODE = "mode"
ATTR_POWER = "power"
ATTR_TARGET_TEMPERATURE = "target_temperature"

PROGRAM_MAP: dict[str, AtreaProgram] = {
    "manual": AtreaProgram.MANUAL,
    "schedule": AtreaProgram.WEEKLY,
    "temporary": AtreaProgram.TEMPORARY,
}

POWER_MIN = 12
POWER_MAX = 100

_DATA_FIELDS = (ATTR_PROGRAM, ATTR_MODE, ATTR_POWER, ATTR_TARGET_TEMPERATURE)

APPLY_SCHEMA = vol.Schema(
    vol.All(
        cv.has_at_least_one_key(*_DATA_FIELDS),
        {
            vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
            vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
            vol.Optional(ATTR_PROGRAM): vol.In(list(PROGRAM_MAP)),
            vol.Optional(ATTR_MODE): cv.string,
            vol.Optional(ATTR_POWER): vol.All(
                vol.Coerce(int), vol.Range(min=POWER_MIN, max=POWER_MAX)
            ),
            vol.Optional(ATTR_TARGET_TEMPERATURE): vol.Coerce(float),
        },
    )
)


def _mode_from_display_name(name: str) -> AtreaMode | None:
    """Invert ``mode_display_name`` to map a display label back to an AtreaMode."""
    return {mode_display_name(m): m for m in AtreaMode}.get(name)


async def _apply_to_coordinator(
    coordinator: AtreaDataUpdateCoordinator,
    *,
    program: str | None = None,
    mode: str | None = None,
    power: int | None = None,
    target_temperature: float | None = None,
) -> None:
    """Stage all provided fields onto one CommandBuilder, commit once, refresh.

    Raises ``ServiceValidationError`` if no field is provided or ``mode`` is not
    a supported display name; ``HomeAssistantError`` on transport failure.
    """
    if program is None and mode is None and power is None and target_temperature is None:
        raise ServiceValidationError(
            "atrea.apply requires at least one of: "
            "program, mode, power, target_temperature."
        )

    data = coordinator.data
    builder = coordinator.client.command_builder(
        modes_to_ids=data.modes_to_ids if data else {},
        supported_modes=data.supported_modes if data else {},
    )

    if program is not None:
        builder.set_program(PROGRAM_MAP[program])

    if mode is not None:
        atrea_mode = _mode_from_display_name(mode)
        supported = data.supported_modes if data else {}
        if atrea_mode is None or not supported.get(atrea_mode, False):
            raise ServiceValidationError(
                f"Operating mode '{mode}' is not supported by the unit."
            )
        builder.set_mode(atrea_mode)

    if power is not None:
        builder.set_power(power)

    if target_temperature is not None:
        builder.set_temperature(target_temperature)

    try:
        await coordinator.client.commit(builder)
    except AtreaConnectionError as err:
        raise HomeAssistantError(f"Atrea write failed: {err}") from err
    await coordinator.async_request_refresh()


def _resolve_coordinators(
    hass: HomeAssistant, call: ServiceCall
) -> list[AtreaDataUpdateCoordinator]:
    """Resolve the service target to the owning Atrea config-entry coordinators.

    Each ``entity_id`` maps to its registry config entry; each ``device_id`` maps
    to all its Atrea config entries. If no target is given and exactly one Atrea
    entry is loaded, that entry is used. Anything ambiguous/empty raises
    ``ServiceValidationError``.
    """
    entity_ids: list[str] = call.data.get(ATTR_ENTITY_ID, [])
    device_ids: list[str] = call.data.get(ATTR_DEVICE_ID, [])

    entry_ids: set[str] = set()

    if entity_ids or device_ids:
        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)
        for entity_id in entity_ids:
            reg_entry = ent_reg.async_get(entity_id)
            if reg_entry is None or reg_entry.config_entry_id is None:
                raise ServiceValidationError(
                    f"Entity '{entity_id}' is not a known Atrea entity."
                )
            entry_ids.add(reg_entry.config_entry_id)
        for device_id in device_ids:
            device = dev_reg.async_get(device_id)
            if device is None:
                raise ServiceValidationError(f"Unknown device '{device_id}'.")
            atrea_entries = [
                eid
                for eid in device.config_entries
                if (e := hass.config_entries.async_get_entry(eid)) is not None
                and e.domain == DOMAIN
            ]
            if not atrea_entries:
                raise ServiceValidationError(
                    f"Device '{device_id}' has no Atrea config entry."
                )
            entry_ids.update(atrea_entries)
    else:
        loaded = [
            e
            for e in hass.config_entries.async_loaded_entries(DOMAIN)
            if getattr(e, "runtime_data", None) is not None
        ]
        if len(loaded) != 1:
            raise ServiceValidationError(
                "No target given and the Atrea entry to apply to is ambiguous; "
                "specify entity_id or device_id."
            )
        entry_ids.add(loaded[0].entry_id)

    coordinators: list[AtreaDataUpdateCoordinator] = []
    for entry_id in entry_ids:
        entry = hass.config_entries.async_get_entry(entry_id)
        if (
            entry is None
            or entry.domain != DOMAIN
            or getattr(entry, "runtime_data", None) is None
        ):
            raise ServiceValidationError(
                "Target does not reference a loaded Atrea unit."
            )
        coordinators.append(entry.runtime_data.coordinator)
    return coordinators


async def _handle_apply(call: ServiceCall) -> None:
    """Service handler: resolve target and apply fields to each coordinator."""
    fields: dict[str, Any] = {
        key: call.data[key] for key in _DATA_FIELDS if key in call.data
    }
    for coordinator in _resolve_coordinators(call.hass, call):
        await _apply_to_coordinator(coordinator, **fields)


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the ``atrea.apply`` service (idempotent on the caller side)."""
    hass.services.async_register(
        DOMAIN, SERVICE_APPLY, _handle_apply, schema=APPLY_SCHEMA
    )


def async_unload_services(hass: HomeAssistant) -> None:
    """Remove the ``atrea.apply`` service."""
    hass.services.async_remove(DOMAIN, SERVICE_APPLY)
