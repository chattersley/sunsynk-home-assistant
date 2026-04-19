# Issue #3 — Add Total Solar Capacity sensor

**Source:** https://github.com/chattersley/sunsynk-home-assistant/issues/3
**Verdict after analysis:** ✅ Small, well-scoped addition. Low risk.

## Reporter's summary

> It would be good to have access to the total solar capacity on the plant
> to set the range for gauges, etc.

## What "Total Solar Capacity" means

Installed DC PV capacity — the nameplate kW rating of the PV array. A
constant per plant (changes only if panels are added / removed), so the
right HA shape is a **diagnostic sensor** (not measurement).

The field exists in the API already:

- `sunsynk_api_client.models.plantinfo.PlantInfo.total_power`
  (aliased `totalPower`, docstring `"Total power capacity (kW)"`).
- Fetched today by `data_fetcher.py:312` via `client.plants.get_plants_async()`
  and stored at `coordinator.data["plants"][plant_id]["info"]`.

## Live verification

The reporter's plant info object includes `total_power`. We already hold
it — just not rendered. No extra API calls needed.

## Proposed fix

Add a plant-level sensor. Slot into the existing plant-sensor factory
alongside the flow sensors:

```python
# sensor.py — new factory or extension of _create_plant_flow_sensors

def _create_plant_info_sensors(
    coordinator: SunSynkCoordinator,
    plant_id: int,
) -> list[SensorEntity]:
    return [
        SunSynkPlantInfoSensor(
            coordinator,
            plant_id,
            attr="total_power",
            translation_key="plant_installed_pv_capacity",
            unit=UnitOfPower.KILO_WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=None,  # not a measurement — constant nameplate
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ]
```

Where `SunSynkPlantInfoSensor` pulls from `plant.info` (the `PlantInfo`
object, already in `coordinator.data`). There is no existing base class
for this exact shape; copy the plant-flow sensor pattern and swap the
`flow` source for `info`.

Translation:

```json
"plant_installed_pv_capacity": { "name": "Installed PV capacity" }
```

### Verify the unit before shipping

The SDK docstring claims kW, but see issue #1 — SDK docstrings for power
fields have been wrong. Before shipping, confirm the raw value matches the
nameplate DC capacity. For the reporter's system that's probably ~4–8 kW.
If the API returns watts here too, switch to `UnitOfPower.WATT`.

A quick manual check against the SunSynk Connect web UI ("Plant detail →
installed capacity") will settle it in one glance.

## Challenge — is this useful?

Yes, for the exact reason the reporter gave (gauge ranges). It's also
useful as a denominator for "% of nameplate" automations ("alert me if PV
drops below 20 % of installed during midday"). It's cheap to add, has a
clear source, and doesn't race with anything.

Alternative: expose it as a device attribute on the plant device rather
than a sensor. Rejected — HA dashboards prefer entities, and gauges can't
bind to device attributes.

Alternative: expose all of `PlantInfo` as diagnostic attributes on an
existing entity. Rejected as scope creep; the reporter asked for one
thing, ship one thing.

## Test strategy

- Add a unit test: coordinator data with a `PlantInfo(total_power=5.2)`
  produces a sensor state of `5.2` with unit `kW`.
- Manual verification: check the sensor value matches SunSynk Connect's
  displayed capacity.

## Open questions

1. Per-inverter vs plant-level? The API reports it only at plant level.
   Multi-inverter plants share one value. No change needed.
2. Integration-level entity or plant-level? Plant-level is right (a
   gateway + inverter assembly can move between plants in rare cases).
