from custom_components.atrea.models import AtreaData, AtreaRuntimeData


def test_atrea_data_holds_fields():
    d = AtreaData(status=None, supported_modes={}, ids_to_modes={},
                  modes_to_ids={}, forced_modes={}, user_labels={},
                  translations={"params": {}, "words": {}}, model=None,
                  version=None, latest_version="0.0", unit_id=None)
    assert d.supported_modes == {}
    assert d.translations["params"] == {}


def test_runtime_data_holds_client_and_coordinator():
    rd = AtreaRuntimeData(client="C", coordinator="K", transport="T")
    assert rd.client == "C"
    assert rd.coordinator == "K"
    assert rd.transport == "T"


def test_const_has_required_names():
    from custom_components.atrea import const
    assert const.DOMAIN == "atrea"
    assert set(const.PLATFORMS) == {
        "climate", "update", "fan", "sensor", "binary_sensor",
        "select", "number", "switch",
    }
    assert isinstance(const.ALL_PRESET_LIST, (list, tuple))


def test_program_season_zone_option_maps():
    from custom_components.atrea import const
    assert const.PROGRAM_OPTIONS == {"Manual": 0, "Schedule": 1, "Temporary": 2}
    assert const.SEASON_OPTIONS == {
        "heating": 0, "non_heating": 1, "auto_oda": 2, "auto_oda_plus": 3,
    }
    assert const.ZONE_OPTIONS == {"1": 0, "2": 1, "1+2": 2}
