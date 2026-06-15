# Atrea HRU for Home Assistant

[![Quality scale: Platinum](https://img.shields.io/badge/quality_scale-platinum-e5e4e2)](https://developers.home-assistant.io/docs/core/integration-quality-scale/)

A fully **async**, **strictly typed** Home Assistant integration for **Atrea**
heat-recovery ventilation (HRU) units built on the **RD5** control system
(Duplex / ECV families). The integration talks to the unit's **local HTTP API**
&mdash; no cloud, no account, `local_polling`.

> This is a maintained fork of
> [JurajNyiri/HomeAssistant-Atrea](https://github.com/JurajNyiri/HomeAssistant-Atrea),
> rewritten from the ground up: an async [`pyatrea`](https://github.com/hoky24/pyatrea)
> client, a `DataUpdateCoordinator`, full strict typing, config/reauth/reconfigure
> flows, diagnostics, repair issues, and a firmware `update` entity. Original
> climate-platform work and protocol reverse-engineering credit goes to Juraj
> Nyiri and the upstream contributors (see [Credits](#credits)).

---

## Supported devices

- Atrea ventilation units running the **RD5** control board, controlled over the
  local web/HTTP API. This covers the common **ECV** and **Duplex** RD5 ranges.
- **Tested on:** Atrea **ECV380 RD5**.

If your unit exposes the RD5 web UI on your LAN and you can reach it by IP, it is
very likely supported. Older non-RD5 controllers are not supported.

## Supported functionality

The integration creates a single **device** per unit, with two entities:

### `climate` entity

| Capability | Detail |
|---|---|
| HVAC modes | `off`, `auto`, `fan_only` |
| Presets | Device programs: Automatic, Ventilation, Circulation, Circulation&nbsp;and&nbsp;Ventilation, Night precooling, Disbalance, Overpressure, Periodic ventilation, and configurable forced inputs (IN1/IN2, D1&ndash;D4) &mdash; the available set is read from the unit and filtered by your options. |
| Fan speed | **12&ndash;100 %** in **1 %** steps (per-percent control). |
| Target temperature | Settable; min/max are read from the unit. |

**State attributes** exposed for dashboards and automations:
`outside_temp`, `inside_temp`, `supply_air_temp`, `extract_temp`,
`exhaust_temp`, `requested_temp`, `requested_power`, `current_power`,
`program`, `forced_mode`, `active_inputs`, `warnings`, `alerts`.

The climate icon is **dynamic** &mdash; it reflects the active mode
(off / ventilation / circulation / defrosting / alert, &hellip;).

### `update` entity (firmware)

- Device class **firmware**: shows the installed firmware version and, when the
  unit advertises a real newer version, offers **Install** with progress.
- Translatable entity name (`translation_key: firmware`).

## Installation

Install via **HACS** as a custom repository:

1. HACS &rarr; **Integrations** &rarr; menu (&vellip;) &rarr; **Custom repositories**.
2. Add `https://github.com/hoky24/HomeAssistant-Atrea`, category **Integration**.
3. Install **Atrea**, then **restart Home Assistant**.
4. Go to **Settings &rarr; Devices &amp; Services &rarr; Add Integration** and search for **Atrea**
   (or use the button below if you have My Home Assistant set up).

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=atrea)

YAML configuration is **not** supported &mdash; use the UI config flow.

### Installation / configuration parameters

The config flow asks for:

| Field | Required | Default | Description |
|---|---|---|---|
| **IP address** | yes | &mdash; | LAN address of the Atrea unit (e.g. `192.168.1.50`). |
| **Port** | yes | `80` | HTTP port of the unit's web interface. |
| **Password** | no | _(empty)_ | Unit web password, if one is configured. Leave blank if none. |
| **Name** | no | `Atrea` | Friendly name for the device. |

The integration **validates connectivity (and the password) before the entry is
created** (`test-before-configure`), so a wrong IP or password is reported in the
form rather than failing silently later.

## Configuration

After setup, **Configure** on the integration's device offers an **options** flow:

- **Fan modes** &mdash; the list of selectable fan-speed percentages.
- **Presets** &mdash; which device programs to expose as climate presets.

Connection-level changes are handled by dedicated flows:

- **Reconfigure** &mdash; change the **IP address** / **port** if the unit moved on the
  network, without deleting and re-adding the integration.
- **Reauthentication** &mdash; if the password changes, Home Assistant raises a reauth
  prompt to re-enter credentials; the existing entry and its history are kept.

## Data updates

- The integration **polls locally** every **10 seconds** (`local_polling`).
- A single `DataUpdateCoordinator` owns **all** I/O. Entities are render-only
  `CoordinatorEntity`s computing their state from `coordinator.data`, so the unit
  is never hit by parallel reads.
- **Firmware-static** data (model, control labels, writable-mode map) is fetched
  **once** and cached; it is re-fetched only after a firmware install
  invalidates the cache.

## Known limitations

- **Slow RD5 state machine.** The unit commits requested changes with a delay of
  roughly **1&ndash;6 minutes**. Transient states (e.g. "temporary", "automatic",
  "unavailable") during that window are **normal** &mdash; the entity converges once
  the unit settles. Don't treat the immediate post-command reading as final.
- **Serialized writes.** A single HTTP session talks to the unit, so write
  commands are serialized to avoid confusing the controller.
- **No auto-discovery.** RD5 units advertise no zeroconf/mDNS/SSDP service and no
  reliable DHCP signature, so setup is **manual IP entry** only.

## Troubleshooting

- **Unit unreachable.** After prolonged failures the integration raises a
  **repair issue** ("Atrea unit unreachable"). Check the unit is powered and on
  the network, that the IP hasn't changed (DHCP lease), and use **Reconfigure** to
  update the IP/port. The entities go **unavailable** while unreachable and
  recover automatically.
- **Wrong password / auth errors.** Home Assistant triggers a **reauth** flow &mdash;
  re-enter the unit's web password.
- **Reporting a bug.** From the device page, **Download diagnostics** and attach
  the (redacted) file to your issue. It captures coordinator state and the unit's
  reported registers without leaking the password.

## Use cases

- **Scheduled ventilation** &mdash; raise fan speed in the morning/evening and drop to
  a minimum overnight with time-based automations.
- **Air-quality boost** &mdash; bump the fan speed or switch presets when a CO&#8322; or
  humidity sensor crosses a threshold, then return to `auto`.
- **Orchestrated control** &mdash; let a parent automation/script own fan speed and
  presets (e.g. coordinating with windows, weather, or a heat pump), reading the
  rich state attributes for decisions.

## Architecture

```
pyatrea (async, py.typed)        →  stateless HTTP client (HA shared aiohttp session)
        │
AtreaDataUpdateCoordinator       →  owns all I/O, polls every 10 s, caches static data,
        │                           raises/clears unreachable repair issues
        ▼
AtreaEntity (CoordinatorEntity)  →  climate + update entities, render-only state
```

- **Platinum**-tier quality: async dependency, HA-injected websession,
  strict typing (`mypy --strict` clean with **no** Home Assistant overrides;
  `pyatrea` ships `py.typed`).
- See [`custom_components/atrea/quality_scale.yaml`](custom_components/atrea/quality_scale.yaml)
  for the full per-rule status.

## Credits

- Original integration and RD5 protocol work:
  [Juraj Nyiri](https://github.com/JurajNyiri) and upstream contributors
  ([JurajNyiri/HomeAssistant-Atrea](https://github.com/JurajNyiri/HomeAssistant-Atrea)).
- Async rewrite and this fork: maintained at
  [hoky24/HomeAssistant-Atrea](https://github.com/hoky24/HomeAssistant-Atrea)
  with the companion [hoky24/pyatrea](https://github.com/hoky24/pyatrea) client.

## License

Distributed under the same license as the upstream project; see
[`LICENSE.md`](LICENSE.md) for details.
