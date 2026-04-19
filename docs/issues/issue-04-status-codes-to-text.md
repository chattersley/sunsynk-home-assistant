# Issue #4 — Render numeric status codes as text

**Source:** https://github.com/chattersley/sunsynk-home-assistant/issues/4
**Verdict after analysis:** ✅ Good idea, with one caveat on "possibly choice
values if writable" — tackle the sensor-side now, the writable side exists
already (as a select), it just needs relabelling.

## Reporter's summary

Numeric codes surfaced as sensors for:

- Gateway — Status
- Inverter — Battery Status
- Inverter — Grid Status
- Inverter — Smart Load Status
- Inverter — System Work Mode

Reporter wants text values, and "possibly choice values if the attribute
is writable."

## Live verification

Current state on the reporter's instance:

| Entity | Value | Unit | Notes |
|---|---|---|---|
| `sensor.sunsynk_gateway_<gateway-sn>_status` | `2` | — | Gateway status |
| `sensor.sunsynk_inverter_EXAMPLE_SN_battery_status` | `2` | — | |
| `sensor.sunsynk_inverter_EXAMPLE_SN_grid_status` | `-1` | — | |
| `sensor.sunsynk_inverter_EXAMPLE_SN_smart_load_status` | `-1` | — | |
| `select.sunsynk_inverter_EXAMPLE_SN_system_work_mode` | `0` | options `["0","1","2","3"]` | Already writable, but labels are raw numbers |

So "System Work Mode" already has a select entity (that's the "writable"
side of the reporter's ask) — we just need to relabel its options. The
other four are read-only sensors and want to become **enum sensors**.

## Meanings of the codes (to be confirmed)

From reading the SunSynk web UI and the integration source code, my best
guesses:

| Field | Code | Proposed label |
|---|---|---|
| **System Work Mode** (`sysWorkMode`) | 0 | Selling First |
| | 1 | Zero Export To Load |
| | 2 | Zero Export To CT |
| | 3 | Self-use |
| **Battery Status** | 0 | Standby / Idle |
| | 1 | Charging |
| | 2 | Discharging |
| **Grid Status** | -1 | Unknown / Offline |
| | 0 | Disconnected |
| | 1 | Grid Connected |
| **Smart Load Status** | -1 | Not Configured |
| | 0 | Off |
| | 1 | On |
| **Gateway Status** | 0 | Offline |
| | 1 | Online |
| | 2 | Online (Connected) |

**Caveat:** I'm not 100% certain on every mapping. `sysWorkMode` labels 0–3
come from cross-referencing the SunSynk Connect web UI dropdown; the
others are inferred. Before shipping we need to:

1. Cross-check against the SunSynk portal's own string table (scrape the
   web UI's localised strings if possible) OR
2. Scan the `sunsynk_api_client` OpenAPI spec for an enum annotation OR
3. Ask the reporter + a couple of other users to confirm what their web UI
   shows at each observed code.

Any code we haven't confirmed should render as `f"Unknown ({n})"` so we
don't hide diagnostic information.

## Proposed fix

### 5 sensors → enum pattern

Home Assistant supports enum sensors natively:

```python
from homeassistant.components.sensor import SensorDeviceClass

class SunSynkBatteryStatusSensor(SunSynkInverterSensor):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["standby", "charging", "discharging", "unknown"]

    def _compute_native_value(self) -> str:
        raw = ... # existing code to pull the int
        return {0: "standby", 1: "charging", 2: "discharging"}.get(raw, "unknown")
```

Pair with translations:

```json
"battery_status": {
  "name": "Battery status",
  "state": {
    "standby": "Standby",
    "charging": "Charging",
    "discharging": "Discharging",
    "unknown": "Unknown"
  }
}
```

This keeps the entity as a string-valued sensor with `device_class=enum`
(which HA cards render sensibly), and the translations file is the single
source of truth for the localised label. Users on German / French HA can
override via their own translation files.

Apply the same pattern to gateway status, grid status, smart load status,
system work mode (sensor variant if there is one, otherwise just the
select — see below).

### System Work Mode — select entity relabelling

The existing `SunSynkSysWorkModeSelect` uses raw strings `["0","1","2","3"]`
as its options. HA's select platform supports translation keys the same
way:

```json
"select": {
  "sys_work_mode": {
    "name": "System work mode",
    "state": {
      "0": "Selling First",
      "1": "Zero Export To Load",
      "2": "Zero Export To CT",
      "3": "Self-use"
    }
  }
}
```

No code change on the select itself — the raw value still goes to the API.
Only the rendered labels change. This is the cheapest possible path and
addresses the "choice values if writable" part of the ask.

## Challenge — push back on one aspect

The reporter's example list includes **Gateway - Status**. That one is
genuinely ambiguous because the gateway statuses differ between firmware
versions and I've not found an authoritative mapping. Options:

1. Ship labels we've confirmed, leave gateway status as raw number with a
   TODO.
2. Ship best-effort labels for gateway + render `"Unknown (2)"` fallback
   to preserve the diagnostic.

Lean toward **option 2** — label what we know, be honest about the rest.
Pure numbers lose context; speculative labels actively mislead.

A stronger alternative: only convert the **three fields we're highly
confident about** (sys_work_mode, battery_status, grid_status) and leave
smart_load and gateway as numeric for now. This ships value quickly
without over-reach. Prefer this if we can't verify in time.

## Breaking-change warning

Switching a sensor's state from `"2"` (string of an int) to `"discharging"`
(a label) will break any user automation that currently compares against
the number. Mitigate:

- Flag prominently in the release notes: "Battery / grid / smart-load /
  gateway status sensors now return text values. Update automations that
  compared against numeric codes."
- Keep the **raw numeric code as an attribute** on the sensor
  (`extra_state_attributes["raw_code"] = 2`) so power users who liked the
  number can still access it.

## Test strategy

- Unit tests: for each status code mapping, assert that the sensor
  returns the right enum string given a mocked coordinator payload.
- A test that an unknown code (e.g. `sys_work_mode = 99`) yields
  `"unknown"` and is not dropped.
- Visual check on the reporter's instance after merge: each sensor shows
  the expected label for the current state; change system work mode from
  "Selling First" to "Zero Export To CT" via the select and observe the
  label update.

## Open questions

1. Can we get a definitive mapping for gateway status and smart load
   status, or do we ship partial labels?
2. Do we want a `raw_code` attribute on every enum sensor (for backwards
   compat), or rely on release notes alone?
3. Any other numeric fields that should follow? (e.g. `battery_status2`
   for multi-battery setups — out of scope for this issue, noted for
   later.)
