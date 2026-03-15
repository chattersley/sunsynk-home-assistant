"""The SunSynk integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_PLANT_IGNORE_LIST,
    CONF_REGION,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .data_fetcher import ErrorTracker, TokenManager, fetch_all_data_sync

_LOGGER = logging.getLogger(__name__)

type SunSynkCoordinator = DataUpdateCoordinator[dict[str, Any]]


@dataclass
class SunSynkRuntimeData:
    """Runtime data for the SunSynk integration."""

    coordinator: SunSynkCoordinator
    token_manager: TokenManager


type SunSynkConfigEntry = ConfigEntry[SunSynkRuntimeData]

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: SunSynkConfigEntry) -> bool:
    """Set up SunSynk from a config entry."""
    region_idx: int = entry.data[CONF_REGION]
    email: str = entry.data[CONF_EMAIL]
    password: str = entry.data[CONF_PASSWORD]

    token_manager = TokenManager(email, password, region_idx)
    error_tracker = ErrorTracker()

    ignore_raw = entry.options.get(CONF_PLANT_IGNORE_LIST, "")
    plant_ignore_list = {
        s.strip() for s in str(ignore_raw).split(",") if s.strip()
    }

    async def async_update_data() -> dict[str, Any]:
        """Fetch data from SunSynk via executor."""
        try:
            return await hass.async_add_executor_job(
                fetch_all_data_sync,
                token_manager,
                region_idx,
                error_tracker,
                plant_ignore_list,
            )
        except Exception as err:
            raise UpdateFailed(
                f"Error communicating with SunSynk: {err}"
            ) from err

    update_interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    coordinator: SunSynkCoordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(seconds=update_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = SunSynkRuntimeData(
        coordinator=coordinator,
        token_manager=token_manager,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: SunSynkConfigEntry,
) -> None:
    """Handle options update - reload the integration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SunSynkConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
