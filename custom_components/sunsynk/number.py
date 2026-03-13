"""Number platform for SunSynk integration — SOC battery cap controls."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_REGION, DOMAIN
from .data_fetcher import TokenManager, write_settings_sync

_LOGGER = logging.getLogger(__name__)

# cap1–cap6: SOC battery discharge floor for each time slot
CAP_DEFS: list[tuple[str, str, str]] = [
    ("cap1", "Cap 1 (SOC Floor)", "cap1"),
    ("cap2", "Cap 2 (SOC Floor)", "cap2"),
    ("cap3", "Cap 3 (SOC Floor)", "cap3"),
    ("cap4", "Cap 4 (SOC Floor)", "cap4"),
    ("cap5", "Cap 5 (SOC Floor)", "cap5"),
    ("cap6", "Cap 6 (SOC Floor)", "cap6"),
]

# Additional numeric settings
EXTRA_NUMBER_DEFS: list[tuple[str, str, str, float, float]] = [
    ("batteryRestartCap", "Battery Restart Cap", "battery_restart_cap", 0, 100),
    ("batteryShutdownCap", "Battery Shutdown Cap", "battery_shutdown_cap", 0, 100),
    ("batteryMaxCurrentCharge", "Battery Max Charge Current", "battery_max_current_charge", 0, 250),
]


class SunSynkCapNumber(CoordinatorEntity, NumberEntity):
    """Number entity for SOC cap settings (cap1–cap6)."""

    _attr_native_min_value = 10
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = PERCENTAGE
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
        """Initialise the cap number entity."""
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
    def native_value(self) -> float | None:
        """Return the current cap value from coordinator data."""
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
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Write the new cap value to the inverter."""
        int_val = str(int(value))
        _LOGGER.debug("Setting %s=%s for inverter %s", self._api_key, int_val, self._sn)
        await self.hass.async_add_executor_job(
            write_settings_sync,
            self._token_manager,
            self._region_idx,
            self._sn,
            {self._api_key: int_val},
        )
        await self.coordinator.async_request_refresh()


class SunSynkExtraNumber(CoordinatorEntity, NumberEntity):
    """Number entity for additional numeric inverter settings."""

    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Any,
        plant_id: int,
        sn: str,
        api_key: str,
        name: str,
        settings_key: str,
        min_val: float,
        max_val: float,
        token_manager: TokenManager,
        region_idx: int,
    ) -> None:
        """Initialise the extra number entity."""
        super().__init__(coordinator)
        self._plant_id = plant_id
        self._sn = sn
        self._api_key = api_key
        self._settings_key = settings_key
        self._token_manager = token_manager
        self._region_idx = region_idx
        self._attr_unique_id = f"{DOMAIN}_inverter_{sn}_{settings_key}"
        self._attr_name = name
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"inverter_{sn}")},
            name=f"SunSynk Inverter {sn}",
            manufacturer="SunSynk",
            model="Inverter",
            serial_number=sn,
            via_device=(DOMAIN, f"plant_{plant_id}"),
        )

    @property
    def native_value(self) -> float | None:
        """Return the current value from coordinator data."""
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
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Write the new value to the inverter."""
        str_val = str(int(value))
        _LOGGER.debug("Setting %s=%s for inverter %s", self._api_key, str_val, self._sn)
        await self.hass.async_add_executor_job(
            write_settings_sync,
            self._token_manager,
            self._region_idx,
            self._sn,
            {self._api_key: str_val},
        )
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SunSynk number platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    token_manager = data["token_manager"]
    region_idx = entry.data[CONF_REGION]

    if not coordinator.data:
        return

    entities: list[NumberEntity] = []

    for plant_id, plant_data in coordinator.data.get("plants", {}).items():
        for sn, inv_data in plant_data.get("inverters", {}).items():
            if not inv_data.get("settings"):
                continue

            # Cap 1–6 number entities
            for api_key, name, settings_key in CAP_DEFS:
                entities.append(SunSynkCapNumber(
                    coordinator, plant_id, sn, api_key, name,
                    settings_key, token_manager, region_idx,
                ))

            # Extra numeric settings
            for api_key, name, settings_key, min_val, max_val in EXTRA_NUMBER_DEFS:
                entities.append(SunSynkExtraNumber(
                    coordinator, plant_id, sn, api_key, name,
                    settings_key, min_val, max_val, token_manager, region_idx,
                ))

    async_add_entities(entities)
