from __future__ import annotations

from pyatrea import AtreaStatus
from pyatrea.parser import translate

_TEMP_SENTINEL = 126.0  # raw 1260 (/10) = sensor not wired


def temp(status: AtreaStatus | None, key: str) -> float | None:
    if status is None:
        return None
    value = status.value(key)
    if value is None or float(value) >= _TEMP_SENTINEL:
        return None
    return float(value)


def efficiency(status: AtreaStatus | None) -> float | None:
    if status is None:
        return None
    supply = temp(status, "I10212")
    outside = temp(status, "I10211")
    extract = temp(status, "I10213")
    if supply is None or outside is None or extract is None:
        return None
    denom = extract - outside
    if abs(denom) < 0.1:
        return None
    return round((supply - outside) / denom * 100, 1)


def fan_hours(status: AtreaStatus | None, low: str, high: str) -> int | None:
    if status is None or low not in status.registers:
        return None
    lo = int(status.registers[low])
    hi = int(status.registers.get(high, "0"))
    return lo + hi * 65536


def fan_drive(status: AtreaStatus | None, key: str) -> int | None:
    if status is None or key not in status.registers:
        return None
    return int(status.registers[key]) // 100


def active_flags(
    status: AtreaStatus | None,
    register_ids: list[str],
    translations: dict[str, dict[str, object]],
) -> list[str]:
    if status is None:
        return []
    out: list[str] = []
    for rid in register_ids:
        if status.registers.get(rid) == "1":
            out.append(translate(translations, rid))
    return out
