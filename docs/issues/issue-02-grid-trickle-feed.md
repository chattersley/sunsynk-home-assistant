# Issue #2 — Expose Grid Trickle Feed (zero-export) setting

**Source:** https://github.com/chattersley/sunsynk-home-assistant/issues/2
**Verdict after analysis:** ✅ Sensible addition. Low risk. Small scope.

## Reporter's summary

> Is it possible to add get/set for the Grid Trickle Feed setting on the
> inverter? We have a slight inaccuracy in our setup and it would be good
> to correct that using some automation.

## What "Grid Trickle Feed" actually is

On the SunSynk Connect web UI this field is labelled **"Zero Export Power"**
(a.k.a. trickle, dead-band, or grid-tied deadband). It represents the
target power — in watts — that the inverter will *draw from the grid* to
guarantee net export remains at zero or below. Typical values 10 W – 100 W.
It only takes effect when **Solar Sell = off**.

The field exists as `zeroExportPower` in the API:

- `sunsynk_api_client.models.invertersettings.zero_export_power`
  (`alias="zeroExportPower"`, type `str` of an integer)
- The reporter's own `setrequest.json` contains `"zeroExportPower": "20"`,
  confirming the field is live on their inverter.

## Live verification

Not currently exposed in the integration. Grepping
`custom_components/sunsynk/` returns no hits for `zeroExport` or
`trickle`. Nothing in the select/switch/number/sensor platforms reads or
writes this field.

## Proposed fix

Add a single `number` entity per inverter. Follow the existing
`SunSynkExtraNumber` pattern already used for `batteryRestartCap` and
`batteryMaxCurrentCharge`:

```python
# number.py:40 — add a row
EXTRA_NUMBER_DEFS: list[tuple[str, str, str, float, float]] = [
    ("batteryRestartCap", ...),
    ("batteryShutdownCap", ...),
    ("batteryMaxCurrentCharge", ...),
    ("zeroExportPower", "zero_export_power", "zero_export_power", 0, 500),
]
```

Plus the translation entries (`strings.json` + `translations/en.json`):

```json
"zero_export_power": { "name": "Zero export power" }
```

Match the field's declared unit:

- `_attr_native_unit_of_measurement = UnitOfPower.WATT`
- `_attr_native_step = 10` (SunSynk web UI clamps in 10 W increments)
- `_attr_mode = NumberMode.BOX` (values 0–500 don't fit a slider nicely)
- `device_class = SensorDeviceClass.POWER`

Write path flows through the existing `async_write_settings` helper — no
new plumbing needed.

## Range/min/max — open question

The SunSynk web UI caps `zeroExportPower` at 500 W on some firmwares, 100 W
on others. Proposal: default `native_max_value = 500` and document. If a
particular firmware rejects a higher value, the API returns an error and
our existing error handling surfaces that. Alternative: add a selector-safe
200 W cap to avoid any chance of a user entering something the firmware
refuses — conservative but slightly patronising.

Suggested: **500 W max**, documented in the translation.

## Challenge — is this a good idea?

Yes, with two mild caveats:

1. **Only useful when Solar Sell = off.** The reporter didn't say whether
   they have an export tariff. If Solar Sell is on, `zeroExportPower` is
   ignored by the inverter — the user could set it and see nothing change
   and report a "doesn't work" bug. Mitigation: one sentence in the entity
   name or strings entry explaining the precondition. e.g. translation
   `"description": "Trickle power drawn from grid when Solar Sell is
   off."` (only rendered in the help popover, not the entity name).
2. **Setting affects physical safety margin around net export.** If the
   user has a G99 / zero-export obligation (common in UK
   installer-commissioned setups), misadjusting this can push them over
   the deadband and toward grid export. Unlikely to cause regulatory
   issues at these power levels, but worth noting.

Neither of these is a blocker — the setting is already user-adjustable
via the SunSynk web UI. Our role is to surface what's already there, not
to add guardrails the vendor didn't think necessary.

## Test strategy

- Add a test to `tests/` that mocks `async_write_settings` and asserts the
  new entity POSTs `{"zeroExportPower": "42"}` when the user writes 42.
- Add a round-trip test: a mocked fetch returning
  `zero_export_power="20"` produces a state of `20` on the number entity.
- Manual: change the value from HA, confirm the web UI (SunSynk Connect)
  reflects the new value within ~60 s (coordinator poll interval).

## Open questions

1. What's the right max? 500 W is conservative; some firmware allows
   higher. Acceptable to start low and relax later.
2. Should we also surface `solarMaxSellPower` (issue adjacent but not
   raised)? Propose no — keep this PR tightly scoped to what was asked.
