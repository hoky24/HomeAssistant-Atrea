from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from pyatrea import AtreaMode, AtreaStatus

if TYPE_CHECKING:
    from pyatrea import AtreaClient

    from .coordinator import AtreaDataUpdateCoordinator


@dataclass(slots=True)
class AtreaData:
    status: AtreaStatus | None
    supported_modes: dict[AtreaMode, bool]
    ids_to_modes: dict[int, AtreaMode]
    modes_to_ids: dict[AtreaMode, int]
    forced_modes: dict[int, AtreaMode]
    user_labels: dict[str, str]
    translations: dict[str, dict[str, object]]
    model: dict[str, str] | None
    version: str | None
    latest_version: str
    unit_id: str | None
    config_dir: ET.Element | None = None


@dataclass(slots=True)
class AtreaRuntimeData:
    client: "AtreaClient"
    coordinator: "AtreaDataUpdateCoordinator"
