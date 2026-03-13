"""The SunSynk integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_PLANT_IGNORE_LIST,
    CONF_REGION,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .data_fetcher import ErrorTracker, TokenManager, fetch_all_data_sync  # noqa: F401

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SunSynk from a config entry."""
    from homeassistant.const import Platform
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

    PLATFORMS: list[Platform] = [
        Platform.SENSOR,
        Platform.NUMBER,
        Platform.SELECT,
        Platform.SWITCH,
    ]

    region_idx = entry.data[CONF_REGION]
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]

    token_manager = TokenManager(email, password, region_idx)
    error_tracker = ErrorTracker()

    async def async_update_data() -> dict:
        """Fetch data from SunSynk via executor."""
        try:
            return await hass.async_add_executor_job(
                fetch_all_data_sync,
                token_manager,
                region_idx,
                error_tracker,
            )
        except Exception as err:
            raise UpdateFailed(
                f"Error communicating with SunSynk: {err}"
            ) from err

    update_interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(seconds=update_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "token_manager": token_manager,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry,
) -> None:
    """Handle options update — reload the integration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    from homeassistant.const import Platform

    PLATFORMS: list[Platform] = [
        Platform.SENSOR,
        Platform.NUMBER,
        Platform.SELECT,
        Platform.SWITCH,
    ]

    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    ):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
