"""Integration-side register-membership guard.

Every register the integration's entities READ via ``status.value(...)`` /
``registers.get(...)`` / ``derive`` helpers must exist in
``pyatrea.registers.REGISTERS``. A missing register means the coordinator never
fetches it and the entity silently reads ``None`` -- the C-1 class of bug. This
test catches that regression from within the integration repo, not only in
pyatrea.

The set below is the live v3 read path, derived from the platform modules:

- sensor.py:      temps I10211/I10212/I10213/I10214/I10215/I11420,
                  fan drives H10200/H10201, fan-hours H13500..H13503
- number.py:      target supply temp H10706
- fan.py:         power readback H10704
- switch.py:      night-precool coil C10902, gate H11022
- climate.py:     mode read H10705
- binary_sensor.py: heating C10215, cooling C10216, defrost D11117/D11118/
                  D11149, filter D11183
- select.py:      program H10700, season H11401/H11402, zone H10707

The legacy ``00xxx`` fallback registers in climate.py (I00200, I00202, H00511,
H01001, H01005, H01006) are deliberately excluded: they are dead fallback paths
for ancient firmware, not the modern read path, and are not modelled by pyatrea.
"""

from __future__ import annotations

from pyatrea.registers import REGISTERS

# Registers the integration's entities actually READ on the live v3 path.
READ_REGISTERS: frozenset[str] = frozenset(
    {
        # temperatures (sensor.py / number.py / derive.temp / derive.efficiency)
        "I10211",  # outside temp
        "I10212",  # supply temp
        "I10213",  # extract temp
        "I10214",  # exhaust temp
        "I10215",  # inside temp
        "I11420",  # avg outside temp
        "H10706",  # target supply temp (number)
        # fan drive percentages (sensor.py / derive.fan_drive)
        "H10200",
        "H10201",
        # fan running hours (sensor.py / derive.fan_hours)
        "H13500",
        "H13501",
        "H13502",
        "H13503",
        # fan power readback (fan.py)
        "H10704",
        # operating-mode read (climate.py mode_of source)
        "H10705",
        # night precooling switch (switch.py)
        "C10902",  # config coil
        "H11022",  # editability gate
        # binary sensors (binary_sensor.py)
        "C10215",  # heating
        "C10216",  # cooling
        "D11117",  # defrost
        "D11118",  # defrost
        "D11149",  # defrost
        "D11183",  # filter
        # selects (select.py)
        "H10700",  # program
        "H11401",  # season
        "H11402",  # season (secondary)
        "H10707",  # zone read
    }
)


def test_all_read_registers_present_in_pyatrea() -> None:
    missing = sorted(r for r in READ_REGISTERS if r not in REGISTERS)
    assert not missing, f"registers read by entities but absent from pyatrea: {missing}"
