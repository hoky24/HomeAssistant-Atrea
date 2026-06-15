from pyatrea import AtreaStatus

from custom_components.atrea import derive


def s(regs):
    return AtreaStatus(registers=regs)


def test_temp_scales_and_sentinel():
    assert derive.temp(s({"I10215": "205"}), "I10215") == 20.5
    assert derive.temp(s({"I10215": "1260"}), "I10215") is None  # 126.0 sentinel
    assert derive.temp(s({}), "I10215") is None
    assert derive.temp(None, "I10215") is None


def test_efficiency():
    st = s({"I10212": "180", "I10211": "0", "I10213": "200"})
    assert derive.efficiency(st) == 90.0


def test_efficiency_guards_zero_denominator():
    st = s({"I10212": "180", "I10211": "200", "I10213": "200"})
    assert derive.efficiency(st) is None


def test_fan_hours_32bit():
    st = s({"H13500": "20842", "H13501": "1"})
    assert derive.fan_hours(st, "H13500", "H13501") == 20842 + 65536


def test_active_flags_translates():
    st = s({"D11183": "1", "D11122": "0"})
    tr = {"params": {"D11183": {"t": "Filter%20due"}}, "words": {}}
    assert derive.active_flags(st, ["D11183", "D11122"], tr) == ["Filter due"]


def test_fan_drive_percent():
    assert derive.fan_drive(s({"H10200": "4800"}), "H10200") == 48
    assert derive.fan_drive(s({}), "H10200") is None
