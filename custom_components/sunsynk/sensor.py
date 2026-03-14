"""Sensor platform for SunSynk integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _safe_float(val: Any) -> float | None:
    """Convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _get_inv_data(coordinator: Any, plant_id: int, sn: str) -> dict | None:
    """Get inverter data dict from coordinator."""
    plant = coordinator.data.get("plants", {}).get(plant_id)
    if not plant:
        return None
    return plant.get("inverters", {}).get(sn)


def _get_source_obj(coordinator: Any, plant_id: int, sn: str, source_type: str) -> Any | None:
    """Get a source object (battery, grid, etc.) from inverter data."""
    inv_data = _get_inv_data(coordinator, plant_id, sn)
    if not inv_data:
        return None
    return inv_data.get(source_type)


def _inverter_device_info(plant_id: int, sn: str) -> DeviceInfo:
    """Return DeviceInfo for an inverter."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"inverter_{sn}")},
        name=f"SunSynk Inverter {sn}",
        manufacturer="SunSynk",
        model="Inverter",
        serial_number=sn,
        via_device=(DOMAIN, f"plant_{plant_id}"),
    )


# ---------------------------------------------------------------------------
# Base sensor
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Gateway sensor
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Event sensor
# ---------------------------------------------------------------------------

class SunSynkEventSensor(SunSynkBaseSensor):
    """Sensor for SunSynk event counts with detail attributes."""

    def __init__(self, coordinator: Any, type_id: int, name: str) -> None:
        """Initialise the event sensor."""
        super().__init__(
            coordinator, f"events_{type_id}", name,
            state_class=SensorStateClass.TOTAL,
        )
        self._type_id = type_id

    @property
    def native_value(self) -> int:
        """Return the event count."""
        events = self.coordinator.data.get("events", {}).get(self._type_id, [])
        return len(events) if events else 0

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return event detail list as attributes."""
        events = self.coordinator.data.get("events", {}).get(self._type_id, [])
        if not events:
            return None
        details = []
        for e in events:
            time_val = getattr(e, "time", None) or _extract_value(e, "time")
            sn_val = getattr(e, "sn", None) or _extract_value(e, "sn")
            code = getattr(e, "event_code", None) or _extract_value(e, "eventCode")
            desc = getattr(e, "event_description", None) or _extract_value(e, "eventDescription")
            if time_val or sn_val or code or desc:
                details.append(f"{time_val} - {sn_val} - {code} - {desc}")
        if details:
            return {"events": details}
        return None


# ---------------------------------------------------------------------------
# Plant flow sensor
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Inverter sensor (simple key-from-source)
# ---------------------------------------------------------------------------

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
        state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT,
    ) -> None:
        """Initialise the inverter sensor."""
        super().__init__(
            coordinator, f"inverter_{sn}_{source_type}_{key}", name, unit,
            device_class, state_class,
        )
        self._plant_id = plant_id
        self._sn = sn
        self._key = key
        self._source_type = source_type
        self._attr_device_info = _inverter_device_info(plant_id, sn)

    @property
    def native_value(self) -> Any | None:
        """Return the current value."""
        source_obj = _get_source_obj(
            self.coordinator, self._plant_id, self._sn, self._source_type,
        )
        if not source_obj:
            return None
        return getattr(source_obj, self._key, None)


# ---------------------------------------------------------------------------
# Inverter temperature sensor
# ---------------------------------------------------------------------------

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
        self._attr_device_info = _inverter_device_info(plant_id, sn)

    @property
    def native_value(self) -> float | Any | None:
        """Return the current value."""
        latest = self._get_latest_temp_record()
        if latest is None:
            return None

        val = _extract_value(latest, self._key)
        return _safe_float(val)

    def _get_latest_temp_record(self) -> Any | None:
        """Return the most recent temperature record for this inverter."""
        day_res = _get_source_obj(
            self.coordinator, self._plant_id, self._sn, "temp",
        )
        if not day_res or not day_res.infos:
            return None
        return day_res.infos[-1]


# ---------------------------------------------------------------------------
# VIP (voltage/current/power from vip[] lists) sensor
# ---------------------------------------------------------------------------

class SunSynkVipSensor(SunSynkBaseSensor):
    """Sensor reading voltage/current/power from a source's vip list."""

    def __init__(
        self,
        coordinator: Any,
        plant_id: int,
        sn: str,
        source_type: str,
        vip_index: int,
        vip_field: str,
        name: str,
        unit: str,
        device_class: SensorDeviceClass,
    ) -> None:
        """Initialise the VIP sensor."""
        super().__init__(
            coordinator,
            f"inverter_{sn}_{source_type}_vip{vip_index}_{vip_field}",
            name, unit, device_class,
        )
        self._plant_id = plant_id
        self._sn = sn
        self._source_type = source_type
        self._vip_index = vip_index
        self._vip_field = vip_field
        self._attr_device_info = _inverter_device_info(plant_id, sn)

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        source_obj = _get_source_obj(
            self.coordinator, self._plant_id, self._sn, self._source_type,
        )
        if not source_obj:
            return None
        vip_list = getattr(source_obj, "vip", None)
        if not vip_list or len(vip_list) <= self._vip_index:
            return None
        return _safe_float(getattr(vip_list[self._vip_index], self._vip_field, None))


# ---------------------------------------------------------------------------
# PV string sensor (from input.pv_iv list)
# ---------------------------------------------------------------------------

class SunSynkPvStringSensor(SunSynkBaseSensor):
    """Sensor for individual PV string data from input.pv_iv[]."""

    def __init__(
        self,
        coordinator: Any,
        plant_id: int,
        sn: str,
        string_index: int,
        field: str,
        name: str,
        unit: str,
        device_class: SensorDeviceClass,
    ) -> None:
        """Initialise the PV string sensor."""
        super().__init__(
            coordinator,
            f"inverter_{sn}_pv{string_index + 1}_{field}",
            name, unit, device_class,
        )
        self._plant_id = plant_id
        self._sn = sn
        self._string_index = string_index
        self._field = field
        self._attr_device_info = _inverter_device_info(plant_id, sn)

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        source_obj = _get_source_obj(
            self.coordinator, self._plant_id, self._sn, "input",
        )
        if not source_obj:
            return None
        pv_iv = getattr(source_obj, "pv_iv", None)
        if not pv_iv or len(pv_iv) <= self._string_index:
            return None
        return _safe_float(getattr(pv_iv[self._string_index], self._field, None))


# ---------------------------------------------------------------------------
# Computed sensor (value derived from multiple fields)
# ---------------------------------------------------------------------------

class SunSynkComputedSensor(SunSynkBaseSensor):
    """Sensor whose value is computed from multiple coordinator data fields."""

    def __init__(
        self,
        coordinator: Any,
        plant_id: int,
        sn: str,
        unique_key: str,
        name: str,
        compute_fn: Any,
        unit: str | None,
        device_class: SensorDeviceClass | None,
        state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT,
    ) -> None:
        """Initialise the computed sensor."""
        super().__init__(
            coordinator, f"inverter_{sn}_computed_{unique_key}", name, unit,
            device_class, state_class,
        )
        self._plant_id = plant_id
        self._sn = sn
        self._compute_fn = compute_fn
        self._attr_device_info = _inverter_device_info(plant_id, sn)

    @property
    def native_value(self) -> float | None:
        """Return the computed value."""
        inv_data = _get_inv_data(self.coordinator, self._plant_id, self._sn)
        if not inv_data:
            return None
        try:
            val = self._compute_fn(inv_data)
            return _safe_float(val)
        except (TypeError, AttributeError, ZeroDivisionError, IndexError):
            return None


# ---------------------------------------------------------------------------
# Notification sensor
# ---------------------------------------------------------------------------

class SunSynkNotificationSensor(SunSynkBaseSensor):
    """Sensor for SunSynk notifications with detail attributes."""

    def __init__(self, coordinator: Any) -> None:
        """Initialise the notification sensor."""
        super().__init__(
            coordinator, "notifications", "Notifications",
            state_class=SensorStateClass.TOTAL,
        )

    @property
    def native_value(self) -> int:
        """Return the notification count."""
        notifications = self.coordinator.data.get("notifications", [])
        return len(notifications) if notifications else 0

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return notification detail list as attributes."""
        notifications = self.coordinator.data.get("notifications", [])
        if not notifications:
            return None
        details = []
        for n in notifications:
            create_at = getattr(n, "create_at", None) or _extract_value(n, "createAt")
            desc = getattr(n, "description", None) or _extract_value(n, "description")
            station = getattr(n, "station_name", None) or _extract_value(n, "stationName")
            if create_at or desc:
                text = desc or ""
                if station:
                    text = text.replace("(#{stationName})", f"{station} ")
                details.append(f"{create_at} - {text}")
        if details:
            return {"notifications": details}
        return None


# ---------------------------------------------------------------------------
# Error tracking sensor
# ---------------------------------------------------------------------------

class SunSynkErrorSensor(SunSynkBaseSensor):
    """Sensor exposing API error counts per category."""

    def __init__(self, coordinator: Any) -> None:
        """Initialise the error sensor."""
        super().__init__(coordinator, "errors", "API Errors", state_class=None)

    @property
    def native_value(self) -> int:
        """Return total error count across all categories."""
        errors = self.coordinator.data.get("errors", {})
        return sum(info.get("count", 0) for info in errors.values())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return flattened error tracking data as attributes."""
        errors = self.coordinator.data.get("errors")
        if not errors:
            return None
        attrs: dict[str, Any] = {}
        for cat, info in errors.items():
            attrs[f"{cat}_count"] = info.get("count", 0)
            attrs[f"{cat}_payload"] = info.get("payload", "")
            attrs[f"{cat}_date"] = info.get("date", "")
        return attrs


# ---------------------------------------------------------------------------
# Last update timestamp sensor
# ---------------------------------------------------------------------------

class SunSynkLastUpdateSensor(SunSynkBaseSensor):
    """Sensor showing when data was last successfully fetched."""

    def __init__(self, coordinator: Any) -> None:
        """Initialise the last update sensor."""
        super().__init__(
            coordinator, "stats_last_update", "Stats Last Update",
            device_class=SensorDeviceClass.TIMESTAMP,
            state_class=None,
        )

    @property
    def native_value(self):
        """Return the last update as a timezone-aware datetime."""
        return self.coordinator.data.get("last_update")


# ---------------------------------------------------------------------------
# Consolidated plant sensor (aggregates across all inverters)
# ---------------------------------------------------------------------------

class SunSynkConsolidatedSensor(SunSynkBaseSensor):
    """Sensor that sums a field across all inverters in a plant."""

    def __init__(
        self,
        coordinator: Any,
        plant_id: int,
        source_type: str,
        key: str,
        name: str,
        unit: str | None,
        device_class: SensorDeviceClass | None,
        state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT,
    ) -> None:
        """Initialise the consolidated sensor."""
        super().__init__(
            coordinator,
            f"plant_{plant_id}_consolidated_{source_type}_{key}",
            name, unit, device_class, state_class,
        )
        self._plant_id = plant_id
        self._source_type = source_type
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
    def native_value(self) -> float | None:
        """Return the summed value across all inverters."""
        plant = self.coordinator.data.get("plants", {}).get(self._plant_id)
        if not plant:
            return None
        total = 0.0
        found_any = False
        for _sn, inv_data in plant.get("inverters", {}).items():
            source = inv_data.get(self._source_type)
            if not source:
                continue
            val = _safe_float(getattr(source, self._key, None))
            if val is not None:
                total += val
                found_any = True
        return round(total, 3) if found_any else None


# ---------------------------------------------------------------------------
# Helper: compute internal power usage for usable inverter sensor
# ---------------------------------------------------------------------------

def _compute_internal_power_usage(
    coordinator: Any, plant_id: int, sn: str,
) -> float | None:
    """Return internal power usage: pv + grid + battery - load."""
    inv_data = _get_inv_data(coordinator, plant_id, sn)
    if not inv_data:
        return None
    pv   = _safe_float(getattr(inv_data.get("input"),   "pac",         None))
    grid = _safe_float(getattr(inv_data.get("grid"),    "pac",         None))
    batt = _safe_float(getattr(inv_data.get("battery"), "power",       None))
    load = _safe_float(getattr(inv_data.get("load"),    "total_power", None))
    if any(v is None for v in (pv, grid, batt, load)):
        return None
    return round(pv + grid + batt - load, 3)


# ---------------------------------------------------------------------------
# Raw data sensor (replicates old "usable" container sensor contract)
# ---------------------------------------------------------------------------

class SunSynkRawDataSensor(SunSynkBaseSensor):
    """Exposes all fields of an API response object as state attributes.

    Replicates the old 'sunsynk_usable_*' sensor contract so that
    existing template sensors in configuration.yaml continue to work.
    """

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: Any,
        plant_id: int,
        sn: str,
        source_type: str,
        name: str,
    ) -> None:
        """Initialise the raw data sensor."""
        super().__init__(
            coordinator,
            f"usable_{source_type}",
            name,
            state_class=None,
        )
        self._plant_id = plant_id
        self._sn = sn
        self._source_type = source_type
        self._attr_device_info = _inverter_device_info(plant_id, sn)

    @property
    def native_value(self) -> str | None:
        """Return 'ok' when data is available, else None."""
        source = _get_source_obj(
            self.coordinator, self._plant_id, self._sn, self._source_type,
        )
        return "ok" if source else None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return all response fields as flat attributes with legacy aliases."""
        if self._source_type == "grid":
            defaults: dict[str, Any] = {"power": 0, "gridonline": 0}
        elif self._source_type == "load":
            defaults = {"power": 0}
        elif self._source_type == "output":
            defaults = {"internalpowerusage": 0}
        elif self._source_type == "battery":
            defaults = {"soc": 0, "power": 0}
        elif self._source_type == "input":
            defaults = {"power": 0, "1_power": 0, "2_power": 0}
        elif self._source_type == "temp":
            defaults = {"battery": 0, "ac": 0, "dc": 0}
        else:
            defaults = {}

        # --- Temp sensor is a special case: composite from temp + battery sources ---
        if self._source_type == "temp":
            attrs: dict[str, Any] = dict(defaults)
            temp_source = _get_source_obj(
                self.coordinator, self._plant_id, self._sn, "temp",
            )
            if temp_source and hasattr(temp_source, "infos") and temp_source.infos:
                latest = temp_source.infos[-1]
                dc_val = _safe_float(getattr(latest, "dc_temp", None))
                ac_val = _safe_float(getattr(latest, "igbt_temp", None))
                if dc_val is not None:
                    attrs["dc"] = dc_val
                if ac_val is not None:
                    attrs["ac"] = ac_val
            batt_source = _get_source_obj(
                self.coordinator, self._plant_id, self._sn, "battery",
            )
            if batt_source:
                batt_temp = _safe_float(getattr(batt_source, "temp", None))
                if batt_temp is not None:
                    attrs["battery"] = batt_temp
            return attrs

        source = _get_source_obj(
            self.coordinator, self._plant_id, self._sn, self._source_type,
        )
        if not source:
            return defaults

        dumped: dict[str, Any] = (
            source.model_dump() if hasattr(source, "model_dump") else dict(source.__dict__)
        )
        # Merge: defaults first, then dumped on top — ensures keys stripped
        # by model_serializer (None optionals) still have fallback values.
        attrs = {**defaults, **dumped}
        if self._source_type == "grid":
            attrs["power"] = attrs.get("pac", 0)
            attrs["gridonline"] = attrs.get("status", 0)
        elif self._source_type == "load":
            attrs["power"] = attrs.get("total_power", 0)
        elif self._source_type == "output":
            attrs["internalpowerusage"] = _compute_internal_power_usage(
                self.coordinator, self._plant_id, self._sn,
            ) or 0
        elif self._source_type == "input":
            attrs["power"] = attrs.get("pac", 0)
            pv_iv = attrs.get("pv_iv") or []
            attrs["1_power"] = pv_iv[0].get("ppv", 0) if len(pv_iv) > 0 else 0
            attrs["2_power"] = pv_iv[1].get("ppv", 0) if len(pv_iv) > 1 else 0
        return attrs


# ---------------------------------------------------------------------------
# Factory: gateway sensors
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Factory: plant flow sensors
# ---------------------------------------------------------------------------

def _create_plant_flow_sensors(
    coordinator: Any, plant_id: int,
) -> list[SensorEntity]:
    """Create sensor entities for plant energy flow."""
    flow_defs: list[tuple[str, str, str, SensorDeviceClass]] = [
        ("pvPower", "PV Power", UnitOfPower.WATT, SensorDeviceClass.POWER),
        ("battPower", "Battery Power", UnitOfPower.WATT, SensorDeviceClass.POWER),
        ("gridOrMeterPower", "Grid Power", UnitOfPower.WATT, SensorDeviceClass.POWER),
        ("loadOrEpsPower", "Load Power", UnitOfPower.WATT, SensorDeviceClass.POWER),
        ("soc", "SOC", PERCENTAGE, SensorDeviceClass.BATTERY),
        ("genPower", "Generator Power", UnitOfPower.WATT, SensorDeviceClass.POWER),
        ("minPower", "Min Power", UnitOfPower.WATT, SensorDeviceClass.POWER),
        ("smartLoadPower", "Smart Load Power", UnitOfPower.WATT, SensorDeviceClass.POWER),
        ("homeLoadPower", "Home Load Power", UnitOfPower.WATT, SensorDeviceClass.POWER),
        ("upsLoadPower", "UPS Load Power", UnitOfPower.WATT, SensorDeviceClass.POWER),
    ]
    return [
        SunSynkPlantFlowSensor(coordinator, plant_id, key, name, unit, dc)
        for key, name, unit, dc in flow_defs
    ]


# ---------------------------------------------------------------------------
# Factory: inverter sensors
# ---------------------------------------------------------------------------

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

    # --- Battery sensors ---
    if inv_data.get("battery"):
        batt_defs: list[tuple[str, str, str | None, SensorDeviceClass | None, SensorStateClass | None]] = [
            ("soc", "Battery SOC", PERCENTAGE, SensorDeviceClass.BATTERY, SensorStateClass.MEASUREMENT),
            ("voltage", "Battery Voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
            ("charge_volt", "Battery Charge Voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
            ("status", "Battery Status", None, None, None),
            ("charge_current_limit", "Battery Charge Current Limit", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
            ("discharge_current_limit", "Battery Discharge Current Limit", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
            ("correct_cap", "Battery Capacity", UnitOfEnergy.KILO_WATT_HOUR, None, None),
            ("current", "Battery Current", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
            ("power", "Battery Power", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
            ("etotal_chg", "Battery Total Charge", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
            ("etotal_dischg", "Battery Total Discharge", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
            ("etoday_chg", "Battery Today Charge", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
            ("etoday_dischg", "Battery Today Discharge", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
            ("temp", "Battery Temperature", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
        ]
        for key, name, unit, dc, sc in batt_defs:
            entities.append(SunSynkInverterSensor(
                coordinator, plant_id, sn, key, name, "battery", unit, dc, sc,
            ))

    # --- Grid sensors ---
    if inv_data.get("grid"):
        grid_defs: list[tuple[str, str, str | None, SensorDeviceClass | None, SensorStateClass | None]] = [
            ("pac", "Grid Power", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
            ("fac", "Grid Frequency", UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY, SensorStateClass.MEASUREMENT),
            ("status", "Grid Status", None, None, None),
            ("pf", "Grid Power Factor", None, SensorDeviceClass.POWER_FACTOR, SensorStateClass.MEASUREMENT),
            ("etotal_from", "Grid Total Import", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
            ("etotal_to", "Grid Total Export", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
            ("etoday_from", "Grid Today Import", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
            ("etoday_to", "Grid Today Export", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
            ("limiter_total_power", "Grid Limiter Total Power", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
        ]
        for key, name, unit, dc, sc in grid_defs:
            entities.append(SunSynkInverterSensor(
                coordinator, plant_id, sn, key, name, "grid", unit, dc, sc,
            ))
        # Grid voltage from vip[0]
        entities.append(SunSynkVipSensor(
            coordinator, plant_id, sn, "grid", 0, "volt",
            "Grid Voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
        ))

    # --- Load sensors ---
    if inv_data.get("load"):
        load_defs: list[tuple[str, str, str | None, SensorDeviceClass | None, SensorStateClass | None]] = [
            ("total_power", "Load Power", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
            ("total_used", "Load Total Used", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
            ("daily_used", "Load Daily Used", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
            ("load_fac", "Load Frequency", UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY, SensorStateClass.MEASUREMENT),
            ("smart_load_status", "Smart Load Status", None, None, None),
            ("ups_power_total", "Load UPS Power", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
        ]
        for key, name, unit, dc, sc in load_defs:
            entities.append(SunSynkInverterSensor(
                coordinator, plant_id, sn, key, name, "load", unit, dc, sc,
            ))
        # Load voltage from vip[0]
        entities.append(SunSynkVipSensor(
            coordinator, plant_id, sn, "load", 0, "volt",
            "Load Voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
        ))

    # --- Output sensors ---
    if inv_data.get("output"):
        output_defs: list[tuple[str, str, str | None, SensorDeviceClass | None, SensorStateClass | None]] = [
            ("p_inv", "Inverter Power", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
            ("fac", "Output Frequency", UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY, SensorStateClass.MEASUREMENT),
        ]
        for key, name, unit, dc, sc in output_defs:
            entities.append(SunSynkInverterSensor(
                coordinator, plant_id, sn, key, name, "output", unit, dc, sc,
            ))
        # Output voltage from vip[0]
        entities.append(SunSynkVipSensor(
            coordinator, plant_id, sn, "output", 0, "volt",
            "Output Voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
        ))

    # --- Generator sensors ---
    if inv_data.get("gen"):
        gen_defs: list[tuple[str, str, str | None, SensorDeviceClass | None, SensorStateClass | None]] = [
            ("gen_total", "Generator Total Energy", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
            ("gen_daily", "Generator Daily Energy", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL),
            ("total_power", "Generator Power", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
            ("gen_fac", "Generator Frequency", UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY, SensorStateClass.MEASUREMENT),
        ]
        for key, name, unit, dc, sc in gen_defs:
            entities.append(SunSynkInverterSensor(
                coordinator, plant_id, sn, key, name, "gen", unit, dc, sc,
            ))
        # Generator voltage from vip[0]
        entities.append(SunSynkVipSensor(
            coordinator, plant_id, sn, "gen", 0, "volt",
            "Generator Voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
        ))

    # --- PV input sensors ---
    if inv_data.get("input"):
        # Total PV power
        entities.append(SunSynkInverterSensor(
            coordinator, plant_id, sn, "pac", "PV Power",
            "input", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER,
        ))
        entities.append(SunSynkInverterSensor(
            coordinator, plant_id, sn, "etoday", "PV Energy Today",
            "input", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
            SensorStateClass.TOTAL,
        ))
        entities.append(SunSynkInverterSensor(
            coordinator, plant_id, sn, "etotal", "PV Energy Total",
            "input", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY,
            SensorStateClass.TOTAL,
        ))
        # Per-string PV sensors
        input_obj = inv_data["input"]
        pv_iv = getattr(input_obj, "pv_iv", None) or []
        for idx in range(len(pv_iv)):
            string_num = idx + 1
            entities.extend([
                SunSynkPvStringSensor(
                    coordinator, plant_id, sn, idx, "ppv",
                    f"PV{string_num} Power", UnitOfPower.WATT, SensorDeviceClass.POWER,
                ),
                SunSynkPvStringSensor(
                    coordinator, plant_id, sn, idx, "ipv",
                    f"PV{string_num} Current", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
                ),
                SunSynkPvStringSensor(
                    coordinator, plant_id, sn, idx, "vpv",
                    f"PV{string_num} Voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE,
                ),
            ])

    # --- Inverter settings sensors ---
    if inv_data.get("settings"):
        settings_defs: list[tuple[str, str]] = [
            ("sell_time1", "Sell Time 1"),
            ("sell_time2", "Sell Time 2"),
            ("sell_time3", "Sell Time 3"),
            ("sell_time4", "Sell Time 4"),
            ("sell_time5", "Sell Time 5"),
            ("sell_time6", "Sell Time 6"),
            ("cap1", "SOC Cap 1"),
            ("cap2", "SOC Cap 2"),
            ("cap3", "SOC Cap 3"),
            ("cap4", "SOC Cap 4"),
            ("cap5", "SOC Cap 5"),
            ("cap6", "SOC Cap 6"),
            ("time1on", "Timer 1 On"),
            ("time2on", "Timer 2 On"),
            ("time3on", "Timer 3 On"),
            ("time4on", "Timer 4 On"),
            ("time5on", "Timer 5 On"),
            ("time6on", "Timer 6 On"),
            ("gen_time1on", "Gen Timer 1 On"),
            ("gen_time2on", "Gen Timer 2 On"),
            ("gen_time3on", "Gen Timer 3 On"),
            ("gen_time4on", "Gen Timer 4 On"),
            ("gen_time5on", "Gen Timer 5 On"),
            ("gen_time6on", "Gen Timer 6 On"),
            ("peak_and_vallery", "Use Timer"),
            ("energy_mode", "Energy Mode"),
            ("sys_work_mode", "System Work Mode"),
            ("sell_time1_pac", "Sell Time 1 Pac"),
            ("sell_time2_pac", "Sell Time 2 Pac"),
            ("sell_time3_pac", "Sell Time 3 Pac"),
            ("sell_time4_pac", "Sell Time 4 Pac"),
            ("sell_time5_pac", "Sell Time 5 Pac"),
            ("sell_time6_pac", "Sell Time 6 Pac"),
            ("battery_restart_cap", "Battery Restart Cap"),
            ("battery_shutdown_cap", "Battery Shutdown Cap"),
            ("battery_max_current_charge", "Battery Max Charge Current"),
        ]
        for key, name in settings_defs:
            entities.append(SunSynkInverterSensor(
                coordinator, plant_id, sn, key, name,
                "settings", None, None, None,
            ))

    # --- Temperature sensors ---
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

    # --- Computed sensors (Phase 2) ---
    entities.extend(_create_computed_sensors(coordinator, plant_id, sn, inv_data))

    return entities


# ---------------------------------------------------------------------------
# Factory: computed / derived sensors
# ---------------------------------------------------------------------------

def _create_computed_sensors(
    coordinator: Any, plant_id: int, sn: str, inv_data: dict,
) -> list[SensorEntity]:
    """Create computed sensors that derive values from multiple data sources."""
    entities: list[SensorEntity] = []

    # Battery efficiency: 100 - (etotal_chg - etotal_dischg) / etotal_dischg * 100
    if inv_data.get("battery"):
        def _battery_efficiency(data: dict) -> float | None:
            batt = data.get("battery")
            if not batt:
                return None
            chg = _safe_float(getattr(batt, "etotal_chg", None))
            dischg = _safe_float(getattr(batt, "etotal_dischg", None))
            if chg is None or dischg is None or dischg == 0:
                return None
            return round(100 - (chg - dischg) / dischg * 100, 1)

        entities.append(SunSynkComputedSensor(
            coordinator, plant_id, sn, "battery_efficiency",
            "Battery Efficiency", _battery_efficiency,
            PERCENTAGE, None,
        ))

    # Load current: load.total_power / load.vip[0].volt (converted to amps)
    if inv_data.get("load"):
        def _load_current(data: dict) -> float | None:
            load = data.get("load")
            if not load:
                return None
            power = _safe_float(getattr(load, "total_power", None))
            vip = getattr(load, "vip", None)
            if not vip or len(vip) == 0:
                return None
            volt = _safe_float(getattr(vip[0], "volt", None))
            if power is None or volt is None or volt == 0:
                return None
            # power is in kW, volt is in V → current = (power * 1000) / volt
            return round(power * 1000 / volt, 2)

        entities.append(SunSynkComputedSensor(
            coordinator, plant_id, sn, "load_current",
            "Load Current", _load_current,
            UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
        ))

    # Grid current: grid.pac / grid.vip[0].volt
    if inv_data.get("grid"):
        def _grid_current(data: dict) -> float | None:
            grid = data.get("grid")
            if not grid:
                return None
            power = _safe_float(getattr(grid, "pac", None))
            vip = getattr(grid, "vip", None)
            if not vip or len(vip) == 0:
                return None
            volt = _safe_float(getattr(vip[0], "volt", None))
            if power is None or volt is None or volt == 0:
                return None
            return round(power * 1000 / volt, 2)

        entities.append(SunSynkComputedSensor(
            coordinator, plant_id, sn, "grid_current",
            "Grid Current", _grid_current,
            UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
        ))

    # PV total current: sum of all pv_iv[n].ipv
    if inv_data.get("input"):
        def _pv_total_current(data: dict) -> float | None:
            inp = data.get("input")
            if not inp:
                return None
            pv_iv = getattr(inp, "pv_iv", None)
            if not pv_iv:
                return None
            total = 0.0
            for pv in pv_iv:
                val = _safe_float(getattr(pv, "ipv", None))
                if val is not None:
                    total += val
            return round(total, 2)

        entities.append(SunSynkComputedSensor(
            coordinator, plant_id, sn, "pv_total_current",
            "PV Total Current", _pv_total_current,
            UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
        ))

    # Output total current: sum of output.vip[n].current
    if inv_data.get("output"):
        def _output_total_current(data: dict) -> float | None:
            output = data.get("output")
            if not output:
                return None
            vip = getattr(output, "vip", None)
            if not vip:
                return None
            total = 0.0
            for v in vip:
                val = _safe_float(getattr(v, "current", None))
                if val is not None:
                    total += val
            return round(total, 2)

        entities.append(SunSynkComputedSensor(
            coordinator, plant_id, sn, "output_total_current",
            "Output Total Current", _output_total_current,
            UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
        ))

    # Generator total current: sum of gen.vip[n].current
    if inv_data.get("gen"):
        def _gen_total_current(data: dict) -> float | None:
            gen = data.get("gen")
            if not gen:
                return None
            vip = getattr(gen, "vip", None)
            if not vip:
                return None
            total = 0.0
            for v in vip:
                val = _safe_float(getattr(v, "current", None))
                if val is not None:
                    total += val
            return round(total, 2)

        entities.append(SunSynkComputedSensor(
            coordinator, plant_id, sn, "gen_total_current",
            "Generator Total Current", _gen_total_current,
            UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT,
        ))

    # Internal power usage: pv.pac + grid.pac + battery.power - load.total_power
    has_all = all(inv_data.get(k) for k in ("input", "grid", "battery", "load"))
    if has_all:
        def _internal_power(data: dict) -> float | None:
            pv_power = _safe_float(getattr(data.get("input"), "pac", None))
            grid_power = _safe_float(getattr(data.get("grid"), "pac", None))
            batt_power = _safe_float(getattr(data.get("battery"), "power", None))
            load_power = _safe_float(getattr(data.get("load"), "total_power", None))
            if any(v is None for v in (pv_power, grid_power, batt_power, load_power)):
                return None
            return round(pv_power + grid_power + batt_power - load_power, 3)

        entities.append(SunSynkComputedSensor(
            coordinator, plant_id, sn, "internal_power_usage",
            "Internal Power Usage", _internal_power,
            UnitOfPower.KILO_WATT, SensorDeviceClass.POWER,
        ))

    # --- Raw data sensors (usable containers for template sensor compatibility) ---
    for source_type, name in (
        ("grid",   "SunSynk Usable Grid"),
        ("load",   "SunSynk Usable Load"),
        ("output", "SunSynk Usable Inverter"),
    ):
        if inv_data.get(source_type):
            entities.append(SunSynkRawDataSensor(
                coordinator, plant_id, sn, source_type, name,
            ))

    return entities


# ---------------------------------------------------------------------------
# Factory: consolidated plant sensors (multi-inverter aggregation)
# ---------------------------------------------------------------------------

def _create_consolidated_sensors(
    coordinator: Any, plant_id: int, inverter_count: int,
) -> list[SensorEntity]:
    """Create consolidated sensors that sum across all inverters in a plant.

    Only created when a plant has more than one inverter.
    """
    if inverter_count <= 1:
        return []

    consol_defs: list[tuple[str, str, str, str | None, SensorDeviceClass | None, SensorStateClass | None]] = [
        ("input", "pac", "Total PV Power", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
        ("load", "total_power", "Total Load Power", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
        ("battery", "power", "Total Battery Power", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
        ("battery", "current", "Total Battery Current", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
        ("grid", "pac", "Total Grid Power", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
        ("output", "pac", "Total Output Power", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
        ("gen", "total_power", "Total Generator Power", UnitOfPower.KILO_WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    ]
    return [
        SunSynkConsolidatedSensor(
            coordinator, plant_id, source, key, name, unit, dc, sc,
        )
        for source, key, name, unit, dc, sc in consol_defs
    ]


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------

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

    # Gateway sensors
    entities.extend(_create_gateway_sensors(
        coordinator, coordinator.data.get("gateways", []),
    ))

    # Event sensors
    entities.extend([
        SunSynkEventSensor(coordinator, 1, "Info Events"),
        SunSynkEventSensor(coordinator, 2, "Warning Events"),
        SunSynkEventSensor(coordinator, 3, "Alarm Events"),
    ])

    # Notification sensor
    entities.append(SunSynkNotificationSensor(coordinator))

    # Error tracking sensor
    entities.append(SunSynkErrorSensor(coordinator))

    # Last update timestamp sensor
    entities.append(SunSynkLastUpdateSensor(coordinator))

    # Plant, inverter, and consolidated sensors
    for plant_id, plant_data in coordinator.data.get("plants", {}).items():
        if plant_data.get("flow"):
            entities.extend(_create_plant_flow_sensors(coordinator, plant_id))

        inverters = plant_data.get("inverters", {})
        for sn, inv_data in inverters.items():
            entities.extend(
                _create_inverter_sensors(coordinator, plant_id, sn, inv_data)
            )

        # Multi-inverter consolidated sensors
        entities.extend(
            _create_consolidated_sensors(coordinator, plant_id, len(inverters))
        )

    async_add_entities(entities)
