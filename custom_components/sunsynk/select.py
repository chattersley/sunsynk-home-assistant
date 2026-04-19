"""Select platform for SunSynk integration — sell time and work mode controls."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SunSynkConfigEntry, SunSynkCoordinator
from .const import DOMAIN, VALID_CHARGE_TIME_SLOTS, VALID_TIME_SLOTS
from .data_fetcher import TokenManager, async_set_plant_income, async_write_settings
from .helpers import (
    build_income_charges,
    get_inverter_settings,
    get_plant_charges,
    get_plant_income_params,
    inverter_device_info,
    plant_device_info,
    to_charge_type,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

# sellTime1-sellTime6: (api_key, translation_key, settings_key)
SELL_TIME_DEFS: list[tuple[str, str, str]] = [
    ("sellTime1", "sell_time_1", "sell_time1"),
    ("sellTime2", "sell_time_2", "sell_time2"),
    ("sellTime3", "sell_time_3", "sell_time3"),
    ("sellTime4", "sell_time_4", "sell_time4"),
    ("sellTime5", "sell_time_5", "sell_time5"),
    ("sellTime6", "sell_time_6", "sell_time6"),
]

SYS_WORK_MODES = ["0", "1", "2"]


class SunSynkSellTimeSelect(CoordinatorEntity, SelectEntity):  # type: ignore[misc]
    """Select entity for sell time slot settings."""

    _attr_options = VALID_TIME_SLOTS
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: SunSynkCoordinator,
        plant_id: int,
        sn: str,
        api_key: str,
        translation_key: str,
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
        self._attr_translation_key = translation_key
        self._attr_device_info = inverter_device_info(plant_id, sn)

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        was_available = getattr(self, "_attr_available", True)
        has_settings = get_inverter_settings(self.coordinator, self._plant_id, self._sn) is not None
        self._attr_available = has_settings
        if was_available and not has_settings:
            _LOGGER.warning("Entity %s is now unavailable", self._attr_unique_id)
        self._attr_current_option = self._compute_current_option() if has_settings else None
        super()._handle_coordinator_update()

    def _compute_current_option(self) -> str | None:
        """Return the current sell time value."""
        settings = get_inverter_settings(self.coordinator, self._plant_id, self._sn)
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
        await async_write_settings(
            self._token_manager,
            self._region_idx,
            self._sn,
            {self._api_key: option},
            current_settings=get_inverter_settings(self.coordinator, self._plant_id, self._sn),
            async_client=get_async_client(self.hass),
        )
        await self.coordinator.async_request_refresh()


class SunSynkSysWorkModeSelect(CoordinatorEntity, SelectEntity):  # type: ignore[misc]
    """Select entity for system work mode."""

    _attr_options = SYS_WORK_MODES
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: SunSynkCoordinator,
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
        self._attr_translation_key = "sys_work_mode"
        self._attr_device_info = inverter_device_info(plant_id, sn)

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        was_available = getattr(self, "_attr_available", True)
        has_settings = get_inverter_settings(self.coordinator, self._plant_id, self._sn) is not None
        self._attr_available = has_settings
        if was_available and not has_settings:
            _LOGGER.warning("Entity %s is now unavailable", self._attr_unique_id)
        self._attr_current_option = self._compute_current_option() if has_settings else None
        super()._handle_coordinator_update()

    def _compute_current_option(self) -> str | None:
        """Return the current work mode."""
        settings = get_inverter_settings(self.coordinator, self._plant_id, self._sn)
        if not settings:
            return None
        val = getattr(settings, "sys_work_mode", None)
        if val is not None:
            return str(val)
        return None

    async def async_select_option(self, option: str) -> None:
        """Write the selected work mode to the inverter."""
        _LOGGER.debug("Setting sysWorkMode=%s for inverter %s", option, self._sn)
        await async_write_settings(
            self._token_manager,
            self._region_idx,
            self._sn,
            {"sysWorkMode": option},
            current_settings=get_inverter_settings(self.coordinator, self._plant_id, self._sn),
            async_client=get_async_client(self.hass),
        )
        await self.coordinator.async_request_refresh()


PRICING_TYPE_OPTIONS = ["1", "2", "3"]
PRICING_TYPE_LABELS = {"1": "Constant Price", "2": "Time of Use", "3": "Live Price"}


class SunSynkChargeTimeSelect(CoordinatorEntity, SelectEntity):  # type: ignore[misc]
    """Select entity for a charge slot start or end time."""

    _attr_options = VALID_CHARGE_TIME_SLOTS
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: SunSynkCoordinator,
        plant_id: int,
        slot: int,
        field: str,
        token_manager: TokenManager,
        region_idx: int,
    ) -> None:
        """Initialise the charge time select entity."""
        super().__init__(coordinator)
        self._plant_id = plant_id
        self._slot = slot
        self._field = field  # "start_range" or "end_range"
        self._token_manager = token_manager
        self._region_idx = region_idx
        label = "start" if field == "start_range" else "end"
        self._attr_unique_id = f"{DOMAIN}_plant_{plant_id}_charge_{label}_{slot}"
        self._attr_translation_key = f"charge_{label}_{slot}"
        self._attr_device_info = plant_device_info(coordinator, plant_id)

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        charges = get_plant_charges(self.coordinator, self._plant_id)
        self._attr_available = self._slot < len(charges)
        self._attr_current_option = self._compute_current_option() if self._attr_available else None
        super()._handle_coordinator_update()

    def _compute_current_option(self) -> str | None:
        """Return the current time value."""
        charges = get_plant_charges(self.coordinator, self._plant_id)
        if self._slot >= len(charges):
            return None
        val = getattr(charges[self._slot], self._field, None)
        if val and val in VALID_CHARGE_TIME_SLOTS:
            return val
        return None

    async def async_select_option(self, option: str) -> None:
        """Write the selected time to the plant income."""
        if option not in VALID_CHARGE_TIME_SLOTS:
            _LOGGER.warning("Invalid charge time slot: %s", option)
            return
        _LOGGER.debug(
            "Setting charge %s slot %d=%s for plant %s",
            self._field,
            self._slot,
            option,
            self._plant_id,
        )
        charges = get_plant_charges(self.coordinator, self._plant_id)
        kwargs = {self._field: option}
        new_charges = build_income_charges(charges, self._slot, **kwargs)
        currency_id, invest = get_plant_income_params(self.coordinator, self._plant_id)

        await async_set_plant_income(
            self._token_manager,
            self._region_idx,
            str(self._plant_id),
            currency_id,
            invest,
            new_charges,
            async_client=get_async_client(self.hass),
        )
        await self.coordinator.async_request_refresh()


class SunSynkPricingTypeSelect(CoordinatorEntity, SelectEntity):  # type: ignore[misc]
    """Select entity for the plant pricing type."""

    _attr_options = PRICING_TYPE_OPTIONS
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: SunSynkCoordinator,
        plant_id: int,
        token_manager: TokenManager,
        region_idx: int,
    ) -> None:
        """Initialise the pricing type select entity."""
        super().__init__(coordinator)
        self._plant_id = plant_id
        self._token_manager = token_manager
        self._region_idx = region_idx
        self._attr_unique_id = f"{DOMAIN}_plant_{plant_id}_pricing_type"
        self._attr_translation_key = "pricing_type"
        self._attr_device_info = plant_device_info(coordinator, plant_id)

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        charges = get_plant_charges(self.coordinator, self._plant_id)
        self._attr_available = len(charges) > 0
        self._attr_current_option = self._compute_current_option() if self._attr_available else None
        super()._handle_coordinator_update()

    def _compute_current_option(self) -> str | None:
        """Return the current pricing type from the first charge."""
        charges = get_plant_charges(self.coordinator, self._plant_id)
        if not charges:
            return None
        charge_type = getattr(charges[0], "type", None)
        if charge_type is not None:
            return str(charge_type)
        return None

    async def async_select_option(self, option: str) -> None:
        """Write the new pricing type to all charge slots."""
        from sunsynk_api_client.models import PlantIncomeCharge

        _LOGGER.debug("Setting pricing type=%s for plant %s", option, self._plant_id)
        charges = get_plant_charges(self.coordinator, self._plant_id)
        new_charges: list[PlantIncomeCharge] = []

        typed = to_charge_type(option)

        if option == "1":
            # Constant Price: single entry 00:00-24:00
            price = str(getattr(charges[0], "price", 0)) if charges else "0"
            new_charges.append(
                PlantIncomeCharge(
                    price=price,
                    type=typed,
                    start_range="00:00",
                    end_range="24:00",
                )
            )
        elif option == "3":
            # Live Price: single entry with empty ranges
            new_charges.append(
                PlantIncomeCharge(
                    price="0",
                    type=typed,
                    start_range="",
                    end_range="",
                )
            )
        else:
            # Time of Use: preserve existing slots, update type
            for charge in charges:
                new_charges.append(
                    PlantIncomeCharge(
                        price=str(getattr(charge, "price", 0)),
                        type=typed,
                        start_range=getattr(charge, "start_range", None),
                        end_range=getattr(charge, "end_range", None),
                    )
                )
            if not new_charges:
                new_charges.append(
                    PlantIncomeCharge(
                        price="0",
                        type=typed,
                        start_range="00:00",
                        end_range="24:00",
                    )
                )

        currency_id, invest = get_plant_income_params(self.coordinator, self._plant_id)
        await async_set_plant_income(
            self._token_manager,
            self._region_idx,
            str(self._plant_id),
            currency_id,
            invest,
            new_charges,
            async_client=get_async_client(self.hass),
        )
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SunSynkConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SunSynk select platform."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    token_manager = runtime.token_manager
    region_idx: int = entry.data["region"]

    if not coordinator.data:
        return

    entities: list[SelectEntity] = []

    for plant_id, plant_data in coordinator.data.get("plants", {}).items():
        # Pricing type select
        charges = get_plant_charges(coordinator, plant_id)
        if charges:
            entities.append(SunSynkPricingTypeSelect(coordinator, plant_id, token_manager, region_idx))

        # Charge time range selects
        for slot in range(len(charges)):
            for field in ("start_range", "end_range"):
                entities.append(SunSynkChargeTimeSelect(coordinator, plant_id, slot, field, token_manager, region_idx))

        for sn, inv_data in plant_data.get("inverters", {}).items():
            if not inv_data.get("settings"):
                continue

            # Sell time 1-6 select entities
            for api_key, name, settings_key in SELL_TIME_DEFS:
                entities.append(
                    SunSynkSellTimeSelect(
                        coordinator,
                        plant_id,
                        sn,
                        api_key,
                        name,
                        settings_key,
                        token_manager,
                        region_idx,
                    )
                )

            # System work mode
            entities.append(
                SunSynkSysWorkModeSelect(
                    coordinator,
                    plant_id,
                    sn,
                    token_manager,
                    region_idx,
                )
            )

    async_add_entities(entities)
