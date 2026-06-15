"""Home Assistant select platform for Atrea HRU units.

Each select is described by a frozen ``AtreaSelectEntityDescription`` carrying
the register to read for the current option, a label-to-register-value map,
and a ``write_fn`` that stages the chosen value onto a ``CommandBuilder``. The
entity reverse-looks-up the current label from the coordinator's status and
delegates writes through the shared ``AtreaEntity`` commit plumbing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import CONF_IP_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pyatrea import AtreaProgram, CommandBuilder

from . import AtreaConfigEntry
from .const import PROGRAM_OPTIONS, SEASON_OPTIONS, ZONE_OPTIONS
from .coordinator import AtreaDataUpdateCoordinator
from .entity import AtreaEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class AtreaSelectEntityDescription(SelectEntityDescription):
    """Describe an Atrea select entity."""

    read_register: str
    options_map: dict[str, int]
    write_fn: Callable[[CommandBuilder, int], None]


def _set_program(builder: CommandBuilder, value: int) -> None:
    """Stage the program triples for ``value`` (``set_program`` returns bool)."""
    builder.set_program(AtreaProgram(value))


SELECTS: tuple[AtreaSelectEntityDescription, ...] = (
    AtreaSelectEntityDescription(
        key="program",
        read_register="H10700",
        options_map=PROGRAM_OPTIONS,
        write_fn=lambda b, v: _set_program(b, v),
    ),
    AtreaSelectEntityDescription(
        key="season",
        read_register="H11401",
        options_map=SEASON_OPTIONS,
        write_fn=lambda b, v: b.commands.__setitem__("H11401", f"{v:05}"),
    ),
    AtreaSelectEntityDescription(
        key="zone",
        read_register="H10707",
        options_map=ZONE_OPTIONS,
        # zone idw write-target is H10717
        write_fn=lambda b, v: b.commands.__setitem__("H10717", f"{v:05}"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AtreaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Atrea select platform from a config entry."""
    coordinator: AtreaDataUpdateCoordinator = entry.runtime_data.coordinator

    opts = {**entry.data, **entry.options}
    name = opts.get(CONF_NAME) or "atrea"
    ip = str(opts[CONF_IP_ADDRESS])

    async_add_entities(
        [
            AtreaSelect(coordinator, entry.entry_id, name, ip, description)
            for description in SELECTS
        ]
    )


class AtreaSelect(AtreaEntity, SelectEntity):
    """Select entity mapping coordinator registers to labelled options."""

    entity_description: AtreaSelectEntityDescription

    def __init__(
        self,
        coordinator: AtreaDataUpdateCoordinator,
        entry_id: str,
        name: str,
        ip: str,
        description: AtreaSelectEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry_id, name, ip)
        self.entity_description = description
        self._attr_options = list(description.options_map)
        self._attr_translation_key = description.key
        self._attr_unique_id = f"{self._device_slug}_{description.key}"

    @property
    def current_option(self) -> str | None:
        status = self.coordinator.data.status if self.coordinator.data else None
        if status is None:
            return None
        raw = status.value(self.entity_description.read_register)
        if raw is None:
            return None
        current = int(raw)
        for label, value in self.entity_description.options_map.items():
            if value == current:
                return label
        return None

    async def async_select_option(self, option: str) -> None:
        value = self.entity_description.options_map[option]
        builder = self._builder()
        self.entity_description.write_fn(builder, value)
        await self._commit(builder)
