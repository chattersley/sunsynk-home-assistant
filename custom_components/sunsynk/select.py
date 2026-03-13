"""Select platform for SunSynk integration — sell time and work mode controls."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_REGION, DOMAIN, VALID_TIME_SLOTS
from .data_fetcher import TokenManager, write_settings_sync

_LOGGER = logging.getLogger(__name__)

# sellTime1–sellTime6: time slot selection (30-min intervals)
SELL_TIME_DEFS: list[tuple[str, str, str]] = [
    ("sellTime1", "Sell Time 1", "sell_time1"),
    ("sellTime2", "Sell Time 2", "sell_time2"),
    ("sellTime3", "Sell Time 3", "sell_time3"),
    ("sellTime4", "Sell Time 4", "sell_time4"),
    ("sellTime5", "Sell Time 5", "sell_time5"),
    ("sellTime6", "Sell Time 6", "sell_time6"),
]

SYS_WORK_MODES = ["0", "1", "2", "3"]


class SunSynkSellTimeSelect(CoordinatorEntity, SelectEntity):
    """Select entity for sell time slot settings."""

    _attr_options = VALID_TIME_SLOTS
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Any,
        plant_id: int,
        sn: str,
        api_key: str,
        name: str,
        settings_key: str,
        token_manager: TokenManager,
        region_idx: int,
    ) -> None:
        """Initialise the sell time select entity."""
        super().__init__(coordinator)
        self._plant_id = plant_id
        self._sn = sn
        self._api_key = api_key
        self._settings_key = settings_key
        self._token_manager = token_manager
        self._region_idx = region_idx
        self._attr_unique_id = f"{DOMAIN}_inverter_{sn}_{settings_key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"inverter_{sn}")},
            name=f"SunSynk Inverter {sn}",
            manufacturer="SunSynk",
            model="Inverter",
            serial_number=sn,
            via_device=(DOMAIN, f"plant_{plant_id}"),
        )

    @property
    def current_option(self) -> str | None:
        """Return the current sell time value."""
        inv_data = (
            self.coordinator.data.get("plants", {})
            .get(self._plant_id, {})
            .get("inverters", {})
            .get(self._sn, {})
        )
        settings = inv_data.get("settings") if inv_data else None
        if not settings:
            return None
        val = getattr(settings, self._settings_key, None)
        if val and val in VALID_TIME_SLOTS:
            return val
        return None

    async def async_select_option(self, option: str) -> None:
        """Write the selected time to the inverter."""
        if option not in VALID_TIME_SLOTS:
            _LOGGER.warning("Invalid time slot: %s", option)
            return
        _LOGGER.debug("Setting %s=%s for inverter %s", self._api_key, option, self._sn)
        await self.hass.async_add_executor_job(
            write_settings_sync,
            self._token_manager,
            self._region_idx,
            self._sn,
            {self._api_key: option},
        )
        await self.coordinator.async_request_refresh()


class SunSynkSysWorkModeSelect(CoordinatorEntity, SelectEntity):
    """Select entity for system work mode (read-only display)."""

    _attr_options = SYS_WORK_MODES
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Any,
        plant_id: int,
        sn: str,
        token_manager: TokenManager,
        region_idx: int,
    ) -> None:
        """Initialise the system work mode select entity."""
        super().__init__(coordinator)
        self._plant_id = plant_id
        self._sn = sn
        self._token_manager = token_manager
        self._region_idx = region_idx
        self._attr_unique_id = f"{DOMAIN}_inverter_{sn}_sys_work_mode"
        self._attr_name = "System Work Mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"inverter_{sn}")},
            name=f"SunSynk Inverter {sn}",
            manufacturer="SunSynk",
            model="Inverter",
            serial_number=sn,
            via_device=(DOMAIN, f"plant_{plant_id}"),
        )

    @property
    def current_option(self) -> str | None:
        """Return the current work mode."""
        inv_data = (
            self.coordinator.data.get("plants", {})
            .get(self._plant_id, {})
            .get("inverters", {})
            .get(self._sn, {})
        )
        settings = inv_data.get("settings") if inv_data else None
        if not settings:
            return None
        val = getattr(settings, "sys_work_mode", None)
        if val is not None:
            return str(val)
        return None

    async def async_select_option(self, option: str) -> None:
        """Write the selected work mode to the inverter."""
        _LOGGER.debug("Setting sysWorkMode=%s for inverter %s", option, self._sn)
        await self.hass.async_add_executor_job(
            write_settings_sync,
            self._token_manager,
            self._region_idx,
            self._sn,
            {"sysWorkMode": option},
        )
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SunSynk select platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    token_manager = data["token_manager"]
    region_idx = entry.data[CONF_REGION]

    if not coordinator.data:
        return

    entities: list[SelectEntity] = []

    for plant_id, plant_data in coordinator.data.get("plants", {}).items():
        for sn, inv_data in plant_data.get("inverters", {}).items():
            if not inv_data.get("settings"):
                continue

            # Sell time 1–6 select entities
            for api_key, name, settings_key in SELL_TIME_DEFS:
                entities.append(SunSynkSellTimeSelect(
                    coordinator, plant_id, sn, api_key, name,
                    settings_key, token_manager, region_idx,
                ))

            # System work mode
            entities.append(SunSynkSysWorkModeSelect(
                coordinator, plant_id, sn, token_manager, region_idx,
            ))

    async_add_entities(entities)
