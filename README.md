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

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **SunSynk**
3. Enter your SunSynk account email and password

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
