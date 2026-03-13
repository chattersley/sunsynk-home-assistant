"""Switch platform for SunSynk integration — timer and mode toggles."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_REGION, DOMAIN
from .data_fetcher import TokenManager, write_settings_sync

_LOGGER = logging.getLogger(__name__)

# Paired timer toggles: (api_key, name, settings_key, paired_api_key, paired_settings_key)
TIMER_TOGGLE_DEFS: list[tuple[str, str, str, str, str]] = [
    ("time1on", "Time 1 On", "time1on", "genTime1on", "gen_time1on"),
    ("time2on", "Time 2 On", "time2on", "genTime2on", "gen_time2on"),
    ("time3on", "Time 3 On", "time3on", "genTime3on", "gen_time3on"),
    ("time4on", "Time 4 On", "time4on", "genTime4on", "gen_time4on"),
    ("time5on", "Time 5 On", "time5on", "genTime5on", "gen_time5on"),
    ("time6on", "Time 6 On", "time6on", "genTime6on", "gen_time6on"),
]

GEN_TIMER_TOGGLE_DEFS: list[tuple[str, str, str, str, str]] = [
    ("genTime1on", "Gen Time 1 On", "gen_time1on", "time1on", "time1on"),
    ("genTime2on", "Gen Time 2 On", "gen_time2on", "time2on", "time2on"),
    ("genTime3on", "Gen Time 3 On", "gen_time3on", "time3on", "time3on"),
    ("genTime4on", "Gen Time 4 On", "gen_time4on", "time4on", "time4on"),
    ("genTime5on", "Gen Time 5 On", "gen_time5on", "time5on", "time5on"),
    ("genTime6on", "Gen Time 6 On", "gen_time6on", "time6on", "time6on"),
]

# Simple boolean toggles: (api_key, name, settings_key)
SIMPLE_TOGGLE_DEFS: list[tuple[str, str, str]] = [
    ("peakAndVallery", "Use Timer", "peak_and_vallery"),
    ("energyMode", "Energy Mode", "energy_mode"),
]


def _bool_to_api(value: bool) -> str:
    """Convert bool to API string value."""
    return "1" if value else "0"


def _api_to_bool(value: Any) -> bool:
    """Convert API string value to bool."""
    if value is None:
        return False
    return str(value) in ("1", "true", "True", "on")


class SunSynkPairedTimerSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for timer toggles that must be sent with their paired value."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Any,
        plant_id: int,
        sn: str,
        api_key: str,
        name: str,
        settings_key: str,
        paired_api_key: str,
        paired_settings_key: str,
        token_manager: TokenManager,
        region_idx: int,
    ) -> None:
        """Initialise the paired timer switch entity."""
        super().__init__(coordinator)
        self._plant_id = plant_id
        self._sn = sn
        self._api_key = api_key
        self._settings_key = settings_key
        self._paired_api_key = paired_api_key
        self._paired_settings_key = paired_settings_key
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

    def _get_settings(self) -> Any | None:
        """Get the settings object from coordinator data."""
        inv_data = (
            self.coordinator.data.get("plants", {})
            .get(self._plant_id, {})
            .get("inverters", {})
            .get(self._sn, {})
        )
        return inv_data.get("settings") if inv_data else None

    @property
    def is_on(self) -> bool | None:
        """Return True if the timer is on."""
        settings = self._get_settings()
        if not settings:
            return None
        val = getattr(settings, self._settings_key, None)
        return _api_to_bool(val)

    async def _write_with_pair(self, new_value: bool) -> None:
        """Write this toggle's value along with its paired toggle's current value."""
        settings = self._get_settings()
        paired_val = "0"
        if settings:
            paired_raw = getattr(settings, self._paired_settings_key, None)
            paired_val = _bool_to_api(_api_to_bool(paired_raw))

        payload = {
            self._api_key: _bool_to_api(new_value),
            self._paired_api_key: paired_val,
        }
        _LOGGER.debug("Writing paired toggles for inverter %s: %s", self._sn, payload)
        await self.hass.async_add_executor_job(
            write_settings_sync,
            self._token_manager,
            self._region_idx,
            self._sn,
            payload,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the timer."""
        await self._write_with_pair(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the timer."""
        await self._write_with_pair(False)


class SunSynkSimpleSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for simple boolean settings (use timer, energy mode)."""

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
        """Initialise the simple switch entity."""
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
    def is_on(self) -> bool | None:
        """Return True if the setting is on."""
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
        return _api_to_bool(val)

    async def _write_value(self, new_value: bool) -> None:
        """Write the setting value."""
        payload = {self._api_key: _bool_to_api(new_value)}
        _LOGGER.debug("Writing setting for inverter %s: %s", self._sn, payload)
        await self.hass.async_add_executor_job(
            write_settings_sync,
            self._token_manager,
            self._region_idx,
            self._sn,
            payload,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the setting."""
        await self._write_value(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the setting."""
        await self._write_value(False)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SunSynk switch platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    token_manager = data["token_manager"]
    region_idx = entry.data[CONF_REGION]

    if not coordinator.data:
        return

    entities: list[SwitchEntity] = []

    for plant_id, plant_data in coordinator.data.get("plants", {}).items():
        for sn, inv_data in plant_data.get("inverters", {}).items():
            if not inv_data.get("settings"):
                continue

            # Timer toggles (paired: time{N}on + genTime{N}on)
            for api_key, name, settings_key, paired_api, paired_sk in TIMER_TOGGLE_DEFS:
                entities.append(SunSynkPairedTimerSwitch(
                    coordinator, plant_id, sn, api_key, name,
                    settings_key, paired_api, paired_sk,
                    token_manager, region_idx,
                ))

            # Gen timer toggles (paired: genTime{N}on + time{N}on)
            for api_key, name, settings_key, paired_api, paired_sk in GEN_TIMER_TOGGLE_DEFS:
                entities.append(SunSynkPairedTimerSwitch(
                    coordinator, plant_id, sn, api_key, name,
                    settings_key, paired_api, paired_sk,
                    token_manager, region_idx,
                ))

            # Simple toggles (use timer, energy mode)
            for api_key, name, settings_key in SIMPLE_TOGGLE_DEFS:
                entities.append(SunSynkSimpleSwitch(
                    coordinator, plant_id, sn, api_key, name,
                    settings_key, token_manager, region_idx,
                ))

    async_add_entities(entities)
