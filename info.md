# Atrea HRU

Async, strictly typed Home Assistant integration for **Atrea** heat-recovery
ventilation (HRU) units on the **RD5** control system (Duplex / ECV), over the
**local HTTP API** &mdash; no cloud (`local_polling`).

Maintained fork of
[JurajNyiri/HomeAssistant-Atrea](https://github.com/JurajNyiri/HomeAssistant-Atrea),
rewritten async/typed with a `DataUpdateCoordinator`, config/reauth/reconfigure
flows, diagnostics, repair issues, and a firmware update entity.
**Platinum** quality scale.

## Supported devices

- Atrea **RD5** units (ECV / Duplex ranges) reachable on your LAN by IP.
- Tested on **ECV380 RD5**.

## What you get

- **Climate entity** &mdash; HVAC modes `off` / `auto` / `fan_only`, device presets
  (Ventilation, Circulation, &hellip;), fan speed **12&ndash;100 % in 1 % steps**,
  target temperature, and rich attributes (inside/outside/supply/exhaust temps,
  power, program, warnings, alerts, forced mode). Dynamic state-driven icon.
- **Update entity** &mdash; firmware version with optional Install.

## Setup

Add via **Settings &rarr; Devices &amp; Services &rarr; Add Integration &rarr; Atrea**.
The config flow asks for **IP address**, **port** (default `80`), an optional
**password**, and a **name**. Options let you tune the fan-speed and preset
lists; **Reconfigure** changes IP/port and **Reauth** updates the password.

## Notes

- Polls locally every 10 s; a single coordinator owns all I/O.
- The RD5 state machine is slow: changes commit in **1&ndash;6 minutes** and
  transient states during that window are normal.
- No auto-discovery (manual IP entry).

See the [README](https://github.com/hoky24/HomeAssistant-Atrea/blob/main/README.md)
for full documentation, troubleshooting, and use cases.
