"""Render-only Home Assistant climate entity for Atrea HRU units.

This module derives ALL state from the data coordinator (``coordinator.data``)
as PURE computation. It performs NO I/O: no ``requests``, no ``self.atrea``
client calls, no ``manualUpdate``/``time.sleep``. Write handlers (set_*,
turn_on/off) are added in a later task.
"""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_IP_ADDRESS,
    CONF_NAME,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pyatrea import (
    AtreaMode,
    AtreaProgram,
    AtreaStatus,
    CommandBuilder,
)
from pyatrea.parser import translate

from .const import (
    ALL_PRESET_LIST,
    CONF_FAN_MODES,
    CONF_PRESETS,
    DEFAULT_FAN_MODE_LIST,
    DOMAIN,
    HVAC_MODES,
    ICONS,
    LOGGER,
    STATE_UNKNOWN,
    SUPPORT_FLAGS,
)
from . import AtreaConfigEntry
from .coordinator import AtreaDataUpdateCoordinator
from .entity import AtreaEntity

PARALLEL_UPDATES = 1


def _process_fan_modes(fan_modes: str) -> list[str]:
    """Port of legacy ``utils.processFanModes``.

    Parse a comma separated list of integer percentages, validate the 12..100
    range, sort, and render each as an ``"N%"`` string. On any malformed entry
    fall back to the full per-1% granularity list (the orchestrator contract:
    HA validates ``set_fan_mode`` against this list).
    """
    numeric: list[int] = []
    for raw in fan_modes.split(","):
        token = raw.strip().rstrip("%")
        if not token.isnumeric() or int(token) < 12 or int(token) > 100:
            return [f"{i}%" for i in range(12, 101)]
        numeric.append(int(token))
    numeric.sort()
    return [f"{value}%" for value in numeric]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AtreaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Atrea climate platform from a config entry."""
    coordinator: AtreaDataUpdateCoordinator = entry.runtime_data.coordinator

    # Options override data: the options flow saves fan modes/presets into
    # entry.options, so read config from a merged view.
    opts = {**entry.data, **entry.options}

    name = opts.get(CONF_NAME) or "atrea"
    ip = str(opts[CONF_IP_ADDRESS])

    fan_list = opts.get(CONF_FAN_MODES)
    if fan_list is None:
        fan_list = DEFAULT_FAN_MODE_LIST

    preset_list = opts.get(CONF_PRESETS)
    if preset_list is None:
        preset_list = {preset: True for preset in ALL_PRESET_LIST}

    async_add_entities(
        [AtreaClimate(coordinator, entry.entry_id, name, ip, fan_list, preset_list)]
    )


class AtreaClimate(AtreaEntity, ClimateEntity):
    """Render-only climate entity deriving state from the coordinator."""

    # Binds icons.json (entity.climate.atrea.default) as the static default
    # icon. The dynamic ``icon`` property below still overrides per-state
    # (alert/off/preset). Because this is the primary entity with
    # ``_attr_name = None``, the name stays the device name, not a translated
    # entity name.
    _attr_translation_key = "atrea"

    def __init__(
        self,
        coordinator: AtreaDataUpdateCoordinator,
        entry_id: str,
        name: str,
        ip: str,
        fan_list: str,
        preset_list: dict[str, bool],
    ) -> None:
        super().__init__(coordinator, entry_id, name, ip)
        self._attr_unique_id = self._device_slug
        # Primary entity: inherit the device name (has_entity_name idiom).
        self._attr_name = None

        # Orchestrator contract: a coarse list (< 80 entries, e.g. the default
        # 10%-step list) is too granular for the orchestrator. Expand to the
        # full per-1% 12..100 list (89 entries). See legacy async_setup_entry.
        modes = _process_fan_modes(fan_list)
        if len(modes) < 80:
            modes = [f"{i}%" for i in range(12, 101)]
        self._attr_fan_modes = modes

        # Preset list filtered against supported modes (legacy updatePresetList).
        supported = coordinator.data.supported_modes if coordinator.data else {}
        self._attr_preset_modes = self._build_preset_list(preset_list, supported)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            "climate_deprecated",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="climate_deprecated",
            breaks_in_ha_version="2027.1.0",
        )
        LOGGER.warning(
            "The Atrea climate entity is deprecated; use the fan/number/select "
            "entities. It will be removed in a future release."
        )

    @staticmethod
    def _build_preset_list(
        preset_list: dict[str, bool], supported: dict[AtreaMode, bool]
    ) -> list[str]:
        """Filter requested presets to those the unit reports as supported."""
        supported_labels = {
            ALL_PRESET_LIST[mode.value]
            for mode, ok in supported.items()
            if ok and mode.value < len(ALL_PRESET_LIST)
        }
        result: list[str] = []
        for preset, requested in preset_list.items():
            if requested and preset in supported_labels:
                result.append(preset)
        return result

    # -- pure helpers ---------------------------------------------------------

    def _status(self) -> AtreaStatus | None:
        return self.coordinator.data.status if self.coordinator.data else None

    def _program(self) -> AtreaProgram | None:
        status = self._status()
        if status is None:
            return None
        return self.coordinator.client.program_of(status)

    def _mode(self) -> AtreaMode | None:
        status = self._status()
        if status is None:
            return None
        ids_to_modes = self.coordinator.data.ids_to_modes
        return self.coordinator.client.mode_of(status, ids_to_modes)

    def _forced_mode(self) -> AtreaMode | None:
        status = self._status()
        if status is None:
            return None
        forced = self.coordinator.data.forced_modes
        return self.coordinator.client.forced_mode_of(status, forced)

    @staticmethod
    def _has(status: AtreaStatus, key: str) -> bool:
        return key in status.registers

    @staticmethod
    def _raw(status: AtreaStatus, key: str) -> int | None:
        """Read a register RAW as the legacy ``manualUpdate`` did.

        The legacy integration read certain registers directly from the status
        dict (``int(status[key])``) and applied its own ``/10`` scaling,
        bypassing ``params.coefs``/``offsets``. ``AtreaStatus.value()`` DOES
        apply coef/offset, so for these registers we must NOT use it (the real
        unit has ``coef=10`` on the temp/power registers, which would scale
        twice). Guarded membership read mirrors the legacy ``"key" in status``.
        """
        raw = status.registers.get(key)
        if raw is None:
            return None
        return int(raw)

    # -- climate basics -------------------------------------------------------

    @property
    def temperature_unit(self) -> str:
        return UnitOfTemperature.CELSIUS

    @property
    def supported_features(self) -> ClimateEntityFeature:
        return SUPPORT_FLAGS

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return HVAC_MODES

    @property
    def min_temp(self) -> float:
        return 10

    @property
    def max_temp(self) -> float:
        return 40

    # fan_modes / preset_modes are served from the base class via the
    # _attr_fan_modes / _attr_preset_modes attributes set in __init__.

    # -- derived state --------------------------------------------------------

    @property
    def _outside_temp(self) -> float:
        """Outside temperature.

        Ported from legacy ``manualUpdate``. NOTE: the legacy code had a
        dead ``elif`` at lines ~314-317 testing ``H00511 == 1`` twice (the
        second branch could never execute). The first branch is preserved and
        the dead ``elif`` (which would have read ``I00201``) is dropped.
        """
        status = self._status()
        if status is None:
            return 0.0
        if self._has(status, "I10211"):
            raw = self._raw(status, "I10211")
            if raw is None:
                return 0.0
            if raw > 1300:
                # Negative-temperature encoding used by the unit.
                return round((50 - (raw - 65036) / 10) * -1, 1)
            return raw / 10
        if self._has(status, "I00202"):
            value = status.value("I00202")
            if value == 126.0:
                # Legacy condition was H00511 == 1; the dead `elif H00511 == 1`
                # reading I00201 is intentionally dropped (could never run).
                if status.value("H00511") == 1:
                    return status.value("I00200") or 0.0
                return 0.0
            return value if value is not None else 0.0
        return 0.0

    @property
    def _inside_temp(self) -> float:
        status = self._status()
        if status is not None and self._has(status, "I10215"):
            raw = self._raw(status, "I10215")
            if raw is not None:
                return raw / 10
        return 0.0

    @property
    def _supply_air_temp(self) -> float:
        status = self._status()
        if status is None:
            return 0.0
        if self._has(status, "I10212"):
            raw = self._raw(status, "I10212")
            return raw / 10 if raw is not None else 0.0
        if self._has(status, "I00200"):
            return status.value("I00200") or 0.0
        return 0.0

    @property
    def _exhaust_temp(self) -> float:
        status = self._status()
        if status is not None and self._has(status, "I10214"):
            raw = self._raw(status, "I10214")
            if raw is not None:
                return raw / 10
        return 0.0

    @property
    def _extract_temp(self) -> float:
        status = self._status()
        if status is not None and self._has(status, "I10213"):
            raw = self._raw(status, "I10213")
            if raw is not None:
                return raw / 10
        return 0.0

    @property
    def _requested_temp(self) -> float:
        status = self._status()
        if status is None:
            return 0.0
        if self._has(status, "H10706"):
            raw = self._raw(status, "H10706")
            return raw / 10 if raw is not None else 0.0
        if self._has(status, "H01006"):
            return status.value("H01006") or 0.0
        return 0.0

    @property
    def _requested_power(self) -> int | None:
        status = self._status()
        if status is None:
            return None
        if self._has(status, "H10714"):
            raw = self._raw(status, "H10714")
            return int(raw) if raw is not None else None
        if self._has(status, "H01005"):
            value = status.value("H01005")
            return int(value) if value is not None else None
        return None

    @property
    def _current_power(self) -> int | None:
        status = self._status()
        if status is not None and self._has(status, "H10704"):
            raw = self._raw(status, "H10704")
            if raw is not None:
                return int(raw)
        return None

    @property
    def _heating(self) -> int:
        status = self._status()
        if status is not None and self._has(status, "C10215"):
            raw = self._raw(status, "C10215")
            if raw is not None:
                return int(raw)
        return -1

    @property
    def _cooling(self) -> int:
        status = self._status()
        if status is not None and self._has(status, "C10216"):
            raw = self._raw(status, "C10216")
            if raw is not None:
                return int(raw)
        return -1

    @property
    def _active_inputs(self) -> list[str]:
        status = self._status()
        result: list[str] = []
        if status is None:
            return result
        for inpt in range(4):
            key = f"D1020{inpt}"
            if self._has(status, key):
                value = self._raw(status, key)
                if value:
                    result.append(f"D{inpt + 1}")
        return result

    @property
    def _warnings(self) -> list[str]:
        status = self._status()
        if status is None:
            return []
        translations = self.coordinator.data.translations
        result: list[str] = []
        for warning in status.params.warning:
            if status.registers.get(warning) == "1":
                result.append(translate(translations, warning))
        return result

    @property
    def _alerts(self) -> list[str]:
        status = self._status()
        if status is None:
            return []
        translations = self.coordinator.data.translations
        result: list[str] = []
        for alert in status.params.alert:
            if status.registers.get(alert) == "1":
                result.append(translate(translations, alert))
        return result

    @property
    def program(self) -> str:
        """Human-readable air handling control program."""
        program = self._program()
        if program == AtreaProgram.MANUAL:
            return "Manual"
        if program == AtreaProgram.WEEKLY:
            return "Schedule"
        if program == AtreaProgram.TEMPORARY:
            return "Temporary"
        return f"Unknown ({program})"

    @property
    def fan_mode(self) -> str | None:
        status = self._status()
        if status is None:
            return None
        if self._has(status, "H01001"):
            raw = status.value("H01001")
            if raw is not None:
                return f"{int(raw)}%"
        power = self._requested_power
        if power is None:
            return None
        return f"{power}%"

    @property
    def target_temperature(self) -> float:
        return float(self._requested_temp)

    @property
    def current_temperature(self) -> float:
        return float(self._inside_temp)

    @property
    def hvac_mode(self) -> HVACMode | None:
        status = self._status()
        if status is None:
            return None

        mode = self._mode()
        program = self._program()

        result: HVACMode | None = None
        if mode == AtreaMode.OFF:
            result = HVACMode.OFF

        if program == AtreaProgram.MANUAL:
            result = HVACMode.OFF if status.value("H10705") == 0 else HVACMode.FAN_ONLY
        elif program == AtreaProgram.WEEKLY:
            result = HVACMode.AUTO
        elif program == AtreaProgram.TEMPORARY:
            result = HVACMode.OFF if status.value("H10705") == 0 else HVACMode.FAN_ONLY

        if self.fan_mode == "0%":
            result = HVACMode.OFF

        return result

    @property
    def preset_mode(self) -> str:
        mode = self._mode()
        if mode is None:
            return STATE_UNKNOWN
        user_labels = self.coordinator.data.user_labels
        if mode.name and mode.name in user_labels:
            return user_labels[mode.name]
        if mode.value < len(ALL_PRESET_LIST):
            return ALL_PRESET_LIST[mode.value]
        return STATE_UNKNOWN

    @property
    def icon(self) -> str:
        if len(self._alerts) > 0:
            return "mdi:fan-alert"
        if self.fan_mode == "0%":
            return "mdi:fan-off"
        mode = self._mode()
        if mode in ICONS:
            return ICONS[mode]
        return "mdi:fan"

    @property
    def hvac_action(self) -> HVACAction | None:
        """Canonical current HVAC action.

        HA's climate base reads the action from this PROPERTY (otherwise None).
        The orchestrator still observes it via the attribute the base populates
        from this property, so it is no longer set manually in
        ``extra_state_attributes``.
        """
        if self._heating == 1:
            return HVACAction.HEATING
        if self._cooling == 1:
            return HVACAction.COOLING
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        forced_mode = self._forced_mode()
        attributes: dict[str, Any] = {
            "outside_temp": self._outside_temp,
            "inside_temp": self._inside_temp,
            "supply_air_temp": self._supply_air_temp,
            "requested_temp": self._requested_temp,
            "exhaust_temp": self._exhaust_temp,
            "extract_temp": self._extract_temp,
            "requested_power": self._requested_power,
            "warnings": self._warnings,
            "alerts": self._alerts,
            "program": self.program,
            "active_inputs": self._active_inputs,
            "forced_mode": forced_mode.name if forced_mode is not None else None,
            "current_power": self._current_power,
        }
        return attributes

    # -- write helpers --------------------------------------------------------

    def _apply_weekly_to_temporary(self, builder: CommandBuilder) -> None:
        """Mirror legacy intent: a manual change while on the weekly schedule
        switches the program to TEMPORARY before power/mode is applied."""
        status = self.coordinator.data.status if self.coordinator.data else None
        if status is None:
            return
        if self.coordinator.client.program_of(status) == AtreaProgram.WEEKLY:
            builder.set_program(AtreaProgram.TEMPORARY)

    # -- write handlers -------------------------------------------------------

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan power (percent). Below 12% is rejected (legacy)."""
        digits = re.sub("[^0-9]", "", fan_mode)
        if not digits:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_fan_mode",
                translation_placeholders={"value": fan_mode},
            )
        pct = int(digits)
        if pct < 12 or pct > 100:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_fan_mode",
                translation_placeholders={"value": fan_mode},
            )
        builder = self._builder()
        self._apply_weekly_to_temporary(builder)
        builder.set_power(pct)
        await self._commit(builder)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode by mapping to the legacy program/mode intent."""
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return
        builder = self._builder()
        # Avoid redundant program writes to the slow RD5 state machine: only
        # write the program register when it actually differs from the current
        # one (legacy behaviour).
        current_program = self._program()
        if hvac_mode == HVACMode.AUTO:
            if current_program != AtreaProgram.WEEKLY:
                builder.set_program(AtreaProgram.WEEKLY)
        elif hvac_mode == HVACMode.FAN_ONLY:
            if current_program != AtreaProgram.MANUAL:
                builder.set_program(AtreaProgram.MANUAL)
            builder.set_mode(AtreaMode.VENTILATION)
        await self._commit(builder)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the ventilation mode from a preset label."""
        try:
            mode = AtreaMode(ALL_PRESET_LIST.index(preset_mode))
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_preset",
                translation_placeholders={"preset": preset_mode},
            ) from err
        if mode == AtreaMode.OFF:
            await self.async_turn_off()
            return
        builder = self._builder()
        self._apply_weekly_to_temporary(builder)
        builder.set_mode(mode)
        await self._commit(builder)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="missing_temperature",
            )
        builder = self._builder()
        builder.set_temperature(temperature)
        await self._commit(builder)

    async def async_turn_on(self) -> None:
        """Turn the unit on, preserving the current program (legacy intent)."""
        builder = self._builder()
        program = self._program()
        if program == AtreaProgram.WEEKLY:
            builder.set_program(AtreaProgram.WEEKLY)
        elif program == AtreaProgram.TEMPORARY:
            builder.set_program(AtreaProgram.TEMPORARY)
        else:
            builder.set_program(AtreaProgram.MANUAL)
        builder.set_mode(AtreaMode.VENTILATION)
        await self._commit(builder)

    async def async_turn_off(self) -> None:
        """Turn the unit off, preserving the current program (legacy intent)."""
        builder = self._builder()
        program = self._program()
        if program == AtreaProgram.MANUAL:
            builder.set_program(AtreaProgram.MANUAL)
        elif program == AtreaProgram.TEMPORARY:
            builder.set_program(AtreaProgram.TEMPORARY)
        else:
            builder.set_program(AtreaProgram.WEEKLY)
        builder.set_mode(AtreaMode.OFF)
        await self._commit(builder)
