from unittest.mock import AsyncMock, MagicMock

from pyatrea import AtreaStatus
from custom_components.atrea.update import AtreaUpdate
from custom_components.atrea.models import AtreaData


def make_coordinator(version="2.0.1", latest="0.0"):
    coord = MagicMock()
    coord.data = AtreaData(
        status=AtreaStatus(registers={}), supported_modes={}, ids_to_modes={},
        modes_to_ids={}, forced_modes={}, user_labels={},
        translations={"params": {}, "words": {}}, model=None, version=version,
        latest_version=latest, unit_id=None)
    return coord


def test_installed_and_latest_versions_from_coordinator():
    coord = make_coordinator(version="2.0.1", latest="2.0.2")
    e = AtreaUpdate(coord, "e", "Atrea", "1.2.3.4")
    assert e.installed_version == "2.0.1"
    assert e.latest_version == "2.0.2"


def test_latest_falls_back_to_installed_when_unknown():
    # when the unit reports no real latest ("0.0"), don't advertise a downgrade
    coord = make_coordinator(version="2.0.1", latest="0.0")
    e = AtreaUpdate(coord, "e", "Atrea", "1.2.3.4")
    assert e.installed_version == "2.0.1"
    # latest_version must NOT be "0.0" (which would look like a downgrade); it
    # should equal installed (no update available)
    assert e.latest_version == "2.0.1"


def test_unique_id_distinct_from_climate():
    coord = make_coordinator()
    e = AtreaUpdate(coord, "e", "Atrea", "1.2.3.4")
    assert e.unique_id == "atrea_1_2_3_4_update"


def test_device_info_shares_climate_identifiers():
    from custom_components.atrea.const import DOMAIN

    coord = make_coordinator()
    e = AtreaUpdate(coord, "e", "Atrea", "1.2.3.4")
    # MUST match climate's identifiers (slugify("atrea_1.2.3.4")) so both
    # entities appear under one device.
    assert e.device_info["identifiers"] == {(DOMAIN, "atrea_1_2_3_4")}


def test_install_feature_only_when_real_latest_available():
    from homeassistant.components.update import UpdateEntityFeature

    no_update = AtreaUpdate(make_coordinator(version="2.0.1", latest="0.0"),
                            "e", "Atrea", "1.2.3.4")
    assert not (no_update.supported_features & UpdateEntityFeature.INSTALL)

    has_update = AtreaUpdate(make_coordinator(version="2.0.1", latest="2.0.2"),
                             "e", "Atrea", "1.2.3.4")
    assert has_update.supported_features & UpdateEntityFeature.INSTALL


async def test_async_install_commits_and_refreshes():
    coord = make_coordinator(version="2.0.1", latest="2.0.2")
    coord.client.command_builder.return_value = MagicMock()
    coord.client.commit = AsyncMock(return_value=True)
    coord.async_request_refresh = AsyncMock()
    e = AtreaUpdate(coord, "e", "Atrea", "1.2.3.4")

    await e.async_install(version=None, backup=False)

    builder = coord.client.command_builder.return_value
    builder.prepare_update.assert_called_once()
    coord.client.commit.assert_awaited_once_with(builder)
    coord.async_request_refresh.assert_awaited_once()


def test_in_progress_from_register():
    coord = make_coordinator()
    coord.data.status.registers["I10005"] = "5"
    e = AtreaUpdate(coord, "e", "Atrea", "1.2.3.4")
    assert e.in_progress is True


def test_not_in_progress_when_register_low_or_absent():
    coord = make_coordinator()
    e = AtreaUpdate(coord, "e", "Atrea", "1.2.3.4")
    assert e.in_progress is False  # register absent
    coord.data.status.registers["I10005"] = "3"
    assert e.in_progress is False  # 3 is not > 3


async def test_install_invalidates_static_cache():
    coord = make_coordinator(version="2.0.1", latest="2.0.2")
    coord.client.command_builder.return_value = MagicMock()
    coord.client.commit = AsyncMock(return_value=True)
    coord.async_request_refresh = AsyncMock()
    coord.invalidate_static = lambda: setattr(coord, "_static_called", True)
    e = AtreaUpdate(coord, "e", "Atrea", "1.2.3.4")
    await e.async_install(version=None, backup=False)
    assert getattr(coord, "_static_called", False) is True


async def test_async_install_wraps_connection_error():
    from pyatrea import AtreaConnectionError
    from homeassistant.exceptions import HomeAssistantError
    import pytest

    coord = make_coordinator(version="2.0.1", latest="2.0.2")
    coord.client.command_builder.return_value = MagicMock()
    coord.client.commit = AsyncMock(side_effect=AtreaConnectionError("boom"))
    coord.async_request_refresh = AsyncMock()
    e = AtreaUpdate(coord, "e", "Atrea", "1.2.3.4")

    with pytest.raises(HomeAssistantError):
        await e.async_install(version=None, backup=False)
