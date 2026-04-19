# Issue #1 — Inverter power values appear 1,000× too large

**Source:** https://github.com/chattersley/sunsynk-home-assistant/issues/1
**Verdict after analysis:** ✅ Real defect. Multiple overlapping root causes.

## Reporter's summary

Plant-scoped sensors look correct, but the inverter-scoped counterparts
(Battery Power, Grid Power, Grid Current, Load Power, Load Current, Inverter
Power, Power Output, PV Power, Internal Power Usage, Grid Limiter Total
Power) read 1,000× too large. Battery Capacity is labelled `kWh` when the
reporter believes it should be `A` (amp-hours).

## Live verification

Probed the reporter's own instance (HA at `192.168.1.57`, inverter
`2210085392`) at the same instant on 2026-04-19:

| Entity | State | Unit | Comment |
|---|---|---|---|
| `sensor.sunsynk_hattersley_pv_power` (plant) | 521 | `W` | **Correct** |
| `sensor.sunsynk_inverter_2210085392_pv_power` | 521 | `kW` | **Wrong** — same raw value, labelled kW |
| `sensor.sunsynk_hattersley_grid_power` (plant) | 52 | `W` | Correct |
| `sensor.sunsynk_inverter_2210085392_grid_power` | 52 | `kW` | Wrong |
| `sensor.sunsynk_inverter_2210085392_grid_current` | 222.89 | `A` | Wrong — 52 W ÷ 233 V ≈ 0.22 A, not 223 A |
| `sensor.sunsynk_inverter_2210085392_load_current` | 4.27 | `A` | Wrong |
| `sensor.sunsynk_inverter_2210085392_internal_power_usage` | 126 | `kW` | Wrong |
| `sensor.sunsynk_inverter_2210085392_grid_limiter_total_power` | -1136 | `kW` | Wrong |
| `sensor.sunsynk_inverter_2210085392_battery_capacity` | 100 | `kWh` | Wrong — raw 100 is ampere-hours (battery rated 100 Ah ≈ 5.12 kWh at 51.2 V) |

The plant row uses `UnitOfPower.WATT` and shows sensible values. The inverter
row uses `UnitOfPower.KILO_WATT` on the same underlying watts value — hence
the reporter sees 521 kW instead of 521 W.

## Root cause

### Cause A — wrong unit declaration on every inverter power sensor

`custom_components/sunsynk/sensor.py` declares the inverter realtime power
sensors as `UnitOfPower.KILO_WATT` (following the API client docstrings),
but the actual API payload is already in watts. The declared unit is a pure
label in HA — the raw numeric state is stored untouched — so the label ends
up 1,000× too big.

Affected rows (line numbers on `main`):

- `sensor.py:942` `inverter_power_output` — `p_ac`
- `sensor.py:990` `battery_power` — `battery.power`
- `sensor.py:1045` `grid_power` — `grid.pac`
- `sensor.py:1078` `grid_limiter_total_power` — `grid.limiter_total_power`
- `sensor.py:1117` `load_power` — `load.total_power`
- `sensor.py:1143` `load_ups_power` — `load.ups_power_total`
- `sensor.py:1180` `inverter_power` — `output.p_inv`
- `sensor.py:1267` `generator_power`
- `sensor.py:1289` `pv_power` — `input.pac`

The plant flow sensors (`sensor.py:910–919`) pulled from
`client.plants.get_plant_flow_async()` are already correct: they declare
`UnitOfPower.WATT` and line up with the `plant_pv_power = 521 W` observation.

### Cause B — computed current multiplies by 1,000 under the same false assumption

`sensor.py:1465` uses `round(power * 1000 / volt, 2)` for the computed
grid/load current sensors, on the assumption that `power` is already in kW
and needs to become W before dividing by volts. Because `power` is already
in watts, the `×1000` is wrong — the returned current is 1,000× too high
(222.89 A on a 52 W grid flow).

### Cause C — computed internal power falls out of (A) for free

`_compute_internal_power` at `sensor.py:1508` returns `pv + grid + batt –
load`. That arithmetic is fine, but because we're about to relabel the unit
on this sensor (currently kW), we have to change its declared unit to W at
the same time (`sensor.py:1613` block).

### Cause D — `battery_capacity` labelled as kWh

`sensor.py:982` exposes the API's `correct_cap` field under
`UnitOfEnergy.KILO_WATT_HOUR`. The live value on the reporter's rack is
100, which matches the nominal Ah rating of a typical 48 V lithium stack.
The API's auto-generated schema claims kWh but the raw number is almost
certainly ampere-hours — 5.12 kWh of usable energy at 51.2 V is 100 Ah.

This is the one cause we can't fully confirm from HA alone. We need a
live API response to be sure whether this field is Ah or kWh.

## Proposed fix

Phased so each change is independently testable.

### Step 1 — prove the units on the wire

Before rewriting anything, run a one-shot script against the reporter's
account (credentials already configured in their HA) and dump one raw
payload from each of:

- `client.inverter_data.get_battery_realtime_async(sn)`
- `client.inverter_data.get_grid_realtime_async(sn)`
- `client.inverter_data.get_load_realtime_async(sn)`
- `client.inverter_data.get_inverter_output_async(sn)`
- `client.inverter_data.get_inverter_input_async(sn)`

Compare the returned `pac` / `power` numbers to what the inverter shows in
the SunSynk web UI at the same moment. If watts, ratify Step 2. If kW,
something else is wrong and we back out.

Also check the reported `correct_cap` and compare against the known battery
nameplate (Ah × V = Wh).

### Step 2 — fix the unit declarations (inverter sensor block)

Change every `UnitOfPower.KILO_WATT` in the inverter-sensor factories to
`UnitOfPower.WATT`. Do this in one commit so the energy-dashboard impact is
atomic (all power sensors switch from kW to W in the same release).

Touch points:

- `sensor.py:942, 990, 1045, 1078, 1117, 1143, 1180, 1267, 1289`
- `sensor.py:1613` (`computed_internal_power_usage`)

### Step 3 — fix the computed-current helper

`sensor.py:1465` — drop the `× 1000`:

```python
return round(power / volt, 2)
```

Applies to both `grid_current` and `load_current` (`sensor.py:1535, 1527`).

### Step 4 — fix `battery_capacity`

Needs confirmation from Step 1. If raw value is Ah:

```python
# sensor.py:982
("correct_cap", "battery_capacity", "Ah", None, SensorStateClass.MEASUREMENT),
```

HA has no native `UnitOfElectricCharge` as a string constant for Ah, but
`"Ah"` as a free-form unit is accepted; device class should be `None`
because there is no matching enum in HA core. State class becomes
`MEASUREMENT` (it's a nameplate reading, not an accumulating total).

If the raw value turns out to genuinely be kWh the fix becomes: leave unit
as `KILO_WATT_HOUR`, set `device_class = ENERGY_STORAGE` (added in 2023.11),
drop the `TOTAL` state class (it's a constant not a meter).

### Step 5 — document the upstream SDK bug

`sunsynk_api_client.models.batterydata.power` is annotated `"Battery power
(kW)"`, same for grid/load/output. File an issue upstream (or open a PR)
pointing out that the API actually returns watts. Until then, add a
comment in our wrapper explaining why we ignore the SDK docstrings.

## Challenge — is this all really one bug?

Yes, but treat it as four landing points, not one:

- **A + B + C collapse into one release** — you can't ship the unit change
  without fixing the current calc, and the `internal_power_usage` unit
  label must move with the others. If you split them, users see either
  mixed units or wildly wrong current for a release.
- **D is independent** — the Ah/kWh question is a separate diagnosis; don't
  hold the power fix waiting on battery-capacity confirmation.

Risk: changing declared units will reset long-term statistics in HA's
recorder. The energy dashboard will break for the affected power sensors
(though energy counters in kWh are untouched because they already had the
right unit). Add migration notes in the release PR and consider bumping
the integration version to force a reconfigure. Historical graphs will
show a discontinuity at upgrade time.

Alternate approach considered and rejected: multiply the raw values by
0.001 in the data layer so declared units stay kW. That keeps recorder
history intact but adds silent rescaling in the fetch path that contradicts
the SDK docstrings — a future maintainer reading the code would be
confused. Better to pick the honest units once and accept the history
break.

## Test strategy

- Add unit tests under `tests/` for each sensor factory that assert the
  declared `native_unit_of_measurement` matches watts/amps/Wh as
  appropriate. One table-driven test covering every `power_defs` /
  `grid_defs` / `load_defs` entry catches regressions cleanly.
- Add a numeric test for `_compute_current_from_power` with synthetic
  inputs (e.g. `power=2300, volt=230 → current=10.0`).
- Manual verification on the reporter's instance after merge: grid current
  at a known load (e.g. kettle ~2.2 kW at 230 V should show ~9.5 A, not
  9,500 A).
- Run `ruff` + `pytest` in the existing CI path.

## Open questions

1. Is `correct_cap` Ah or kWh? (Needs live API dump.)
2. Are there users in the wild who built dashboards on the *wrong* kW
   values and will interpret the fix as a regression? Probably — worth a
   prominent entry in the release notes.
3. Should we follow up with an upstream PR to `sunsynk_api_client` to fix
   the docstrings? Worth flagging but not blocking.
