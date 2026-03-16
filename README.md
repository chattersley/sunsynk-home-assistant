# SunSynk Home Assistant Integration

A custom [HACS](https://hacs.xyz/) integration for [Home Assistant](https://www.home-assistant.io/) that connects to the SunSynk cloud API to monitor your solar inverter system.

## Features

- Authenticates with the SunSynk cloud using your account credentials
- Polls plant and inverter data every 60 seconds
- Exposes sensors for:
  - **Battery**: state of charge, power, voltage, current, temperature, daily/total charge and discharge energy
  - **PV Input**: power, daily and total generated energy
  - **Output**: AC output power
  - **Grid**: import/export power, daily and total import/export energy

## Requirements

- Home Assistant 2026.2.3 or later
- A SunSynk account with at least one registered plant and inverter
- HACS installed

## Installation

### Via HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** → **Custom repositories**
3. Add `https://github.com/chattersley/remote-sunsynk-home-assistant` as an **Integration**
4. Search for **SunSynk** and install it
5. Restart Home Assistant

### Manual

Copy the `custom_components/sunsynk` folder into your Home Assistant `config/custom_components/` directory, then restart Home Assistant.

## Configuration

### Initial Setup

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **SunSynk**
3. Enter the following parameters:

| Parameter | Description |
|-----------|-------------|
| **Region** | The SunSynk API region to connect to. Choose *Region 1 (pv.inteless.com)* or *Region 2 (api.sunsynk.net)* depending on your account. |
| **Email** | The email address associated with your SunSynk account. |
| **Password** | Your SunSynk account password. |

### Options

After setup, you can configure additional options via the integration's **Configure** button:

| Parameter | Default | Description |
|-----------|---------|-------------|
| **Update interval** | 60 seconds | How often to poll the SunSynk API for new data (30–600 seconds). |
| **Plant IDs to ignore** | *(empty)* | Comma-separated list of plant IDs to exclude from monitoring. Useful if your account has multiple plants and you only want to track specific ones. |

## Data Update

The integration uses Home Assistant's `DataUpdateCoordinator` to poll the SunSynk cloud API at a configurable interval (default: 60 seconds, range: 30–600 seconds). Each polling cycle fetches:

1. **Plant list** and flow data (PV, battery, grid, load power summaries)
2. **Inverter data** for each inverter in each plant — output, input, battery, grid, load, generator, temperature, and settings
3. **System data** — gateways, events (info/warning/alarm), and notifications

Authentication tokens are cached and automatically refreshed before expiry. If authentication fails during a data update, the integration triggers a re-authentication flow. If the API becomes unreachable for 3 or more consecutive updates, a repair issue is created in Home Assistant and automatically resolved when communication recovers.

Stale devices (inverters or plants removed from your SunSynk account) are automatically cleaned up from the device registry after each successful update.

## Use Cases

- **Solar monitoring** — Track real-time PV generation, battery state of charge, grid import/export, and household consumption from the Home Assistant dashboard.
- **Time-of-use optimization** — Use the sell time select and SOC cap number entities to adjust inverter schedules from automations based on electricity tariff periods.
- **Battery management** — Monitor battery health (charge cycles, temperature, efficiency) and set charge current limits or shutdown caps remotely.
- **Multi-inverter plants** — Consolidated total sensors automatically aggregate power and current across all inverters in a plant.
- **Alerting** — Create automations that notify you when the grid goes down, battery SOC drops below a threshold, or the API reports errors.

## Supported Devices

This integration works with any solar system registered in the SunSynk cloud portal, including:

- **Inverters** — SunSynk hybrid inverters (e.g. 5kW, 8kW, 12kW single-phase and three-phase models). Any inverter visible in the SunSynk app/portal should be supported.
- **Batteries** — All battery types connected to supported inverters (lithium, lead-acid). Battery data is read from the inverter's BMS interface.
- **Gateways** — SunSynk Wi-Fi and LAN data loggers/dongles used to connect inverters to the cloud.
- **Generators** — Generator inputs monitored through the inverter.

The integration discovers all plants, inverters, and gateways associated with your SunSynk account automatically.

## Supported Functions

### Sensors (read-only)

| Category | Entities | Description |
|----------|----------|-------------|
| **Plant flow** | PV power, battery power, grid power, load power, SOC, generator power, min power, smart load, home load, UPS load | Real-time power flow summary per plant |
| **Battery** | SOC, voltage, charge voltage, status, charge/discharge current limits, capacity, current, power, total/daily charge and discharge, temperature | Per-inverter battery monitoring |
| **Grid** | Power, frequency, status, power factor, voltage, total/daily import and export, limiter power | Per-inverter grid monitoring |
| **Load** | Power, total/daily used, frequency, smart load status, UPS power, voltage | Per-inverter load monitoring |
| **Inverter output** | Power, output frequency, output voltage | Per-inverter output |
| **Generator** | Power, frequency, voltage, total/daily energy | Per-inverter generator monitoring |
| **PV input** | Total PV power, daily/total energy, per-string power/current/voltage | Per-inverter solar input |
| **Temperature** | DC temperature, IGBT temperature | Per-inverter thermal monitoring |
| **Computed** | Battery efficiency, load/grid/PV/output/generator current, internal power usage | Derived values calculated from raw data |
| **Consolidated totals** | Total PV/load/battery/grid/output/generator power, total battery current | Aggregated across all inverters (multi-inverter plants) |
| **Gateway** | Status, signal strength | Per-gateway monitoring |
| **System** | Info/warning/alarm event counts, notifications, API errors, last update time | Integration health |
| **Settings mirror** | Sell times, SOC caps, timers, energy mode, work mode, sell power, battery caps/current | Read-only copies of inverter settings (disabled by default) |

### Numbers (configurable)

| Entity | Range | Description |
|--------|-------|-------------|
| SOC floor 1–6 | 10–100% | Minimum battery state of charge per time period |
| Battery restart cap | 0–100% | Battery SOC threshold to restart from grid |
| Battery shutdown cap | 0–100% | Battery SOC threshold for shutdown |
| Battery max charge current | 0–250 A | Maximum battery charging current |

### Selects (configurable)

| Entity | Options | Description |
|--------|---------|-------------|
| Sell time 1–6 | 30-minute time slots (00:00–23:30) | Time period boundaries for sell/buy schedules |
| System work mode | 0, 1, 2, 3 | Inverter operating mode |

### Switches (configurable)

| Entity | Description |
|--------|-------------|
| Timer 1–6 | Enable/disable load timer periods |
| Gen timer 1–6 | Enable/disable generator timer periods |
| Use timer | Enable/disable peak and valley timer mode |
| Energy mode | Toggle energy mode |

## Examples

### Energy dashboard

Go to **Settings > Dashboards > Energy** and add the following entities (replace `SERIAL` with your inverter serial number):

| Dashboard section | Field | Entity |
|-------------------|-------|--------|
| **Solar panels** | Solar production | `sensor.sunsynk_inverter_SERIAL_pv_energy_today` |
| **Grid consumption** | Grid consumption | `sensor.sunsynk_inverter_SERIAL_grid_today_import` |
| **Grid consumption** | Return to grid | `sensor.sunsynk_inverter_SERIAL_grid_today_export` |
| **Battery systems** | Energy going in | `sensor.sunsynk_inverter_SERIAL_battery_today_charge` |
| **Battery systems** | Energy coming out | `sensor.sunsynk_inverter_SERIAL_battery_today_discharge` |

All of these sensors use `device_class: energy`, `state_class: total`, and `unit: kWh` as required by the Energy dashboard. The `total` lifetime variants (e.g. `pv_energy_total`, `grid_total_import`) also work.

### Battery SOC automation

```yaml
automation:
  - alias: "Low battery alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sunsynk_inverter_SERIAL_battery_soc
        below: 20
    action:
      - service: notify.mobile_app
        data:
          title: "Low Battery"
          message: "Battery SOC is {{ states('sensor.sunsynk_inverter_SERIAL_battery_soc') }}%"
```

### Time-of-use SOC floor adjustment

```yaml
automation:
  - alias: "Peak tariff - raise SOC floor"
    trigger:
      - platform: time
        at: "17:00:00"
    action:
      - service: number.set_value
        target:
          entity_id: number.sunsynk_inverter_SERIAL_soc_floor_1
        data:
          value: 50

  - alias: "Off-peak - lower SOC floor"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: number.set_value
        target:
          entity_id: number.sunsynk_inverter_SERIAL_soc_floor_1
        data:
          value: 10
```

### Grid power gauge card

```yaml
type: gauge
entity: sensor.sunsynk_inverter_SERIAL_grid_power
name: Grid Power
min: -10
max: 10
severity:
  green: 0
  yellow: 3
  red: 6
```

## Known Limitations

- **Cloud-only** — This integration communicates with the SunSynk cloud API. It does not support local/LAN access to the inverter. If the SunSynk cloud is down, data updates will pause.
- **API rate limits** — The SunSynk API may rate-limit requests. The minimum polling interval is 30 seconds to avoid triggering rate limits. If you experience errors, increase the update interval.
- **Read-only for most data** — Only settings (SOC caps, sell times, timers, work mode, energy mode, battery caps/current) can be written. Power flow and energy data is read-only.
- **No local control** — All write operations go through the cloud API, so there is a small delay and they require an active internet connection.
- **Single account** — Each integration instance connects to one SunSynk account. To monitor multiple accounts, add the integration multiple times.
- **Data granularity** — The API returns aggregated/instantaneous values. Historical data at sub-minute granularity is not available.

## Troubleshooting

### Authentication failures

- Verify your email and password work in the SunSynk mobile app or web portal.
- Try the other API region — some accounts are on Region 1 (pv.inteless.com), others on Region 2 (api.sunsynk.net).
- If credentials change, use the **Reconfigure** option in the integration menu, or Home Assistant will prompt for re-authentication automatically.

### Missing sensors or data

- Ensure your inverter is online and reporting to the SunSynk cloud (check the SunSynk app).
- Some sensors only appear when the inverter provides the relevant data (e.g. generator sensors require a connected generator).
- PV string sensors are created per MPPT string — the count depends on your inverter model.
- Settings mirror sensors are disabled by default. Enable them in the entity registry if needed.

### API errors

- Check the **API errors** sensor for error counts and categories.
- The integration creates a repair issue in Home Assistant after 3 consecutive API failures. Check **Settings > Repairs** for details.
- Temporary API outages resolve automatically — the repair issue clears when communication is restored.
- If errors persist, try increasing the update interval to reduce API load.

### Entities showing "unknown" or "unavailable"

- **Unknown** means the inverter returned no value for that field. This is normal for unused features (e.g. generator sensors when no generator is connected).
- **Unavailable** means the coordinator failed to fetch data. Check your network connection and the SunSynk cloud status.

## Removing the Integration

1. Go to **Settings** → **Devices & Services**
2. Find the **SunSynk** integration entry
3. Click the three-dot menu (⋮) and select **Delete**

No additional cleanup is needed — the integration does not create any persistent files or side-effects outside of Home Assistant.

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install dependencies
uv sync
```

The Python client library is sourced from [chattersley/sunsynk-python](https://github.com/chattersley/sunsynk-python).

### Local data fetch test

`main.py` fetches a full snapshot of your SunSynk data and prints it as JSON — useful for verifying credentials and inspecting the API response without running Home Assistant.

**1. Create your `.env` file**

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:

```ini
SUNSYNK_EMAIL=you@example.com
SUNSYNK_PASSWORD=your_password
SUNSYNK_REGION=0        # 0 = pv.inteless.com  |  1 = api.sunsynk.net
LOG_LEVEL=INFO          # DEBUG or TRACE for verbose output
```

`.env` is listed in `.gitignore` and will never be committed.

**2. Run the script**

```bash
uv run python main.py
```

The output is a JSON object containing plants, inverters, battery, grid, PV, load, events, and error counters. Pipe it through `jq` for easier reading:

```bash
uv run python main.py | jq .
```
