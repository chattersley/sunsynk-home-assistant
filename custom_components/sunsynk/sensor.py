"""Sensor platform for SunSynk integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _extract_value(obj: Any, key: str) -> Any | None:
    """Extract a value from an object by key, trying multiple access patterns."""
    val = getattr(obj, key, None)
    if val is not None:
        return val

    if hasattr(obj, "__dict__"):
        val = obj.__dict__.get(key)
        if val is not None:
            return val

    if hasattr(obj, "model_extra") and obj.model_extra:
        val = obj.model_extra.get(key)
        if val is not None:
            return val

    if isinstance(obj, dict):
        return obj.get(key)

    return None


def _create_gateway_sensors(
    coordinator: Any, gateways: list,
) -> list[SensorEntity]:
    """Create sensor entities for gateways."""
    entities: list[SensorEntity] = []
    for gw in gateways:
        entities.append(
            SunSynkGatewaySensor(coordinator, gw, "status", "Status")
        )
        entities.append(
            SunSynkGatewaySensor(
                coordinator, gw, "signal", "Signal Strength",
                state_class=SensorStateClass.MEASUREMENT, unit=None,
            )
        )
    return entities


def _create_plant_flow_sensors(
    coordinator: Any, plant_id: int,
) -> list[SensorEntity]:
    """Create sensor entities for plant energy flow."""
    return [
        SunSynkPlantFlowSensor(
            coordinator, plant_id, "pvPower", "PV Power",
            UnitOfPower.WATT, SensorDeviceClass.POWER,
        ),
        SunSynkPlantFlowSensor(
            coordinator, plant_id, "battPower", "Battery Power",
            UnitOfPower.WATT, SensorDeviceClass.POWER,
        ),
        SunSynkPlantFlowSensor(
            coordinator, plant_id, "gridOrMeterPower", "Grid Power",
            UnitOfPower.WATT, SensorDeviceClass.POWER,
        ),
        SunSynkPlantFlowSensor(
            coordinator, plant_id, "loadOrEpsPower", "Load Power",
            UnitOfPower.WATT, SensorDeviceClass.POWER,
        ),
        SunSynkPlantFlowSensor(
            coordinator, plant_id, "soc", "SOC",
            PERCENTAGE, SensorDeviceClass.BATTERY,
        ),
    ]


def _create_inverter_sensors(
    coordinator: Any, plant_id: int, sn: str, inv_data: dict,
) -> list[SensorEntity]:
    """Create sensor entities for a single inverter."""
    entities: list[SensorEntity] = [
        SunSynkInverterSensor(
            coordinator, plant_id, sn, "pac", "Power Output",
            "info", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER,
        ),
    ]

    if inv_data.get("battery"):
        entities.extend([
            SunSynkInverterSensor(
                coordinator, plant_id, sn, "etoday",
                "Battery Energy Today", "battery",
                UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
            ),
            SunSynkInverterSensor(
                coordinator, plant_id, sn, "etotal",
                "Battery Energy Total", "battery",
                UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
            ),
        ])

    if inv_data.get("input"):
        entities.extend([
            SunSynkInverterSensor(
                coordinator, plant_id, sn, "etoday",
                "PV Energy Today", "input",
                UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
            ),
            SunSynkInverterSensor(
                coordinator, plant_id, sn, "etotal",
                "PV Energy Total", "input",
                UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
            ),
        ])

    if inv_data.get("settings"):
        entities.append(SunSynkInverterSensor(
            coordinator, plant_id, sn, "sellTime1",
            "Sell Time 1", "settings", None, None,
        ))

    if inv_data.get("temp"):
        entities.extend([
            SunSynkInverterTempSensor(
                coordinator, plant_id, sn, "dc_temp",
                "DC Temperature", UnitOfTemperature.CELSIUS,
                SensorDeviceClass.TEMPERATURE,
            ),
            SunSynkInverterTempSensor(
                coordinator, plant_id, sn, "igbt_temp",
                "IGBT Temperature", UnitOfTemperature.CELSIUS,
                SensorDeviceClass.TEMPERATURE,
            ),
        ])

    return entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SunSynk sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    if not coordinator.data:
        _LOGGER.warning("No data found in SunSynk")
        return

    entities: list[SensorEntity] = []

    entities.extend(_create_gateway_sensors(
        coordinator, coordinator.data.get("gateways", []),
    ))

    entities.extend([
        SunSynkEventSensor(coordinator, 1, "Info Events"),
        SunSynkEventSensor(coordinator, 2, "Warning Events"),
        SunSynkEventSensor(coordinator, 3, "Alarm Events"),
    ])

    for plant_id, plant_data in coordinator.data.get("plants", {}).items():
        if plant_data.get("flow"):
            entities.extend(_create_plant_flow_sensors(coordinator, plant_id))

        for sn, inv_data in plant_data.get("inverters", {}).items():
            entities.extend(
                _create_inverter_sensors(coordinator, plant_id, sn, inv_data)
            )

    async_add_entities(entities)


class SunSynkBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for SunSynk sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Any,
        unique_id_suffix: str,
        name: str,
        unit: str | None = None,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT,
    ) -> None:
        """Initialise the base sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{unique_id_suffix}"
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class


class SunSynkGatewaySensor(SunSynkBaseSensor):
    """Sensor for SunSynk gateway status."""

    def __init__(self, coordinator: Any, gateway: Any, key: str, name: str, **kwargs: Any) -> None:
        """Initialise the gateway sensor."""
        super().__init__(coordinator, f"gateway_{gateway.sn}_{key}", name, **kwargs)
        self._gateway_sn = gateway.sn
        self._key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"gateway_{gateway.sn}")},
            name=f"SunSynk Gateway {gateway.sn}",
            manufacturer="SunSynk",
            model="Gateway",
            serial_number=gateway.sn,
        )

    @property
    def native_value(self) -> Any | None:
        """Return the current value."""
        gateways = self.coordinator.data.get("gateways", [])
        for gw in gateways:
            if gw.sn == self._gateway_sn:
                return getattr(gw, self._key, None)
        return None


class SunSynkEventSensor(SunSynkBaseSensor):
    """Sensor for SunSynk event counts."""

    def __init__(self, coordinator: Any, type_id: int, name: str) -> None:
        """Initialise the event sensor."""
        super().__init__(
            coordinator, f"events_{type_id}", name,
            state_class=SensorStateClass.TOTAL,
        )
        self._type_id = type_id

    @property
    def native_value(self) -> int:
        """Return the current value."""
        events = self.coordinator.data.get("events", {}).get(self._type_id, [])
        return len(events) if events else 0


class SunSynkPlantFlowSensor(SunSynkBaseSensor):
    """Sensor for SunSynk plant energy flow."""

    def __init__(
        self,
        coordinator: Any,
        plant_id: int,
        key: str,
        name: str,
        unit: str,
        device_class: SensorDeviceClass,
    ) -> None:
        """Initialise the plant flow sensor."""
        super().__init__(
            coordinator, f"plant_{plant_id}_flow_{key}", name, unit,
            device_class,
        )
        self._plant_id = plant_id
        self._key = key
        plant_info = (
            coordinator.data.get("plants", {}).get(plant_id, {}).get("info")
        )
        plant_name = getattr(plant_info, "name", None) or f"Plant {plant_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=f"SunSynk {plant_name}",
            manufacturer="SunSynk",
            model="Solar Plant",
        )

    @property
    def native_value(self) -> Any | None:
        """Return the current value."""
        plant = self.coordinator.data.get("plants", {}).get(self._plant_id)
        if plant and plant.get("flow"):
            return getattr(plant["flow"], self._key, None)
        return None


class SunSynkInverterSensor(SunSynkBaseSensor):
    """Sensor for SunSynk inverter data."""

    def __init__(
        self,
        coordinator: Any,
        plant_id: int,
        sn: str,
        key: str,
        name: str,
        source_type: str,
        unit: str | None,
        device_class: SensorDeviceClass | None,
    ) -> None:
        """Initialise the inverter sensor."""
        super().__init__(
            coordinator, f"inverter_{sn}_{source_type}_{key}", name, unit,
            device_class,
        )
        self._plant_id = plant_id
        self._sn = sn
        self._key = key
        self._source_type = source_type
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"inverter_{sn}")},
            name=f"SunSynk Inverter {sn}",
            manufacturer="SunSynk",
            model="Inverter",
            serial_number=sn,
            via_device=(DOMAIN, f"plant_{plant_id}"),
        )

    @property
    def native_value(self) -> Any | None:
        """Return the current value."""
        plant = self.coordinator.data.get("plants", {}).get(self._plant_id)
        if not plant:
            return None

        inv_data = plant.get("inverters", {}).get(self._sn)
        if not inv_data:
            return None

        source_obj = inv_data.get(self._source_type)
        if not source_obj:
            return None

        return getattr(source_obj, self._key, None)


class SunSynkInverterTempSensor(SunSynkBaseSensor):
    """Sensor for SunSynk inverter temperatures."""

    def __init__(
        self,
        coordinator: Any,
        plant_id: int,
        sn: str,
        key: str,
        name: str,
        unit: str,
        device_class: SensorDeviceClass,
    ) -> None:
        """Initialise the inverter temperature sensor."""
        super().__init__(
            coordinator, f"inverter_{sn}_temp_{key}", name, unit,
            device_class,
        )
        self._plant_id = plant_id
        self._sn = sn
        self._key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"inverter_{sn}")},
            name=f"SunSynk Inverter {sn}",
            manufacturer="SunSynk",
            model="Inverter",
            serial_number=sn,
            via_device=(DOMAIN, f"plant_{plant_id}"),
        )

    @property
    def native_value(self) -> float | Any | None:
        """Return the current value."""
        latest = self._get_latest_temp_record()
        if latest is None:
            return None

        val = _extract_value(latest, self._key)
        if val is None:
            return None

        try:
            return float(val)
        except (ValueError, TypeError):
            return val

    def _get_latest_temp_record(self) -> Any | None:
        """Return the most recent temperature record for this inverter."""
        plant = self.coordinator.data.get("plants", {}).get(self._plant_id)
        if not plant:
            return None

        inv_data = plant.get("inverters", {}).get(self._sn)
        if not inv_data:
            return None

        day_res = inv_data.get("temp")
        if not day_res or not day_res.data or not day_res.data.infos:
            return None

        return day_res.data.infos[-1]
