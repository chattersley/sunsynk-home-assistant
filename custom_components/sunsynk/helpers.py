"""Shared helpers for the SunSynk integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

if TYPE_CHECKING:
    from . import SunSynkCoordinator


def extract_value(obj: Any, key: str) -> Any | None:
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
        return cast(dict[str, Any], obj).get(key)

    return None


def safe_float(val: Any) -> float | None:
    """Convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except ValueError, TypeError:
        return None


def get_inv_data(
    coordinator: SunSynkCoordinator,
    plant_id: int,
    sn: str,
) -> dict[str, Any] | None:
    """Get inverter data dict from coordinator."""
    if not coordinator.data:
        return None
    plant = coordinator.data.get("plants", {}).get(plant_id)
    if not plant:
        return None
    return plant.get("inverters", {}).get(sn)


def get_source_obj(
    coordinator: SunSynkCoordinator,
    plant_id: int,
    sn: str,
    source_type: str,
) -> Any | None:
    """Get a source object (battery, grid, etc.) from inverter data."""
    inv_data = get_inv_data(coordinator, plant_id, sn)
    if not inv_data:
        return None
    return inv_data.get(source_type)


def get_inverter_settings(
    coordinator: SunSynkCoordinator,
    plant_id: int,
    sn: str,
) -> Any | None:
    """Get the inverter settings object from coordinator data."""
    inv_data = get_inv_data(coordinator, plant_id, sn)
    if not inv_data:
        return None
    return inv_data.get("settings")


def get_plant_detail(
    coordinator: SunSynkCoordinator,
    plant_id: int,
) -> Any | None:
    """Get the plant detail object (PlantInfo) from coordinator data."""
    if not coordinator.data:
        return None
    plant = coordinator.data.get("plants", {}).get(plant_id)
    if not plant:
        return None
    return plant.get("detail")


def get_plant_charges(
    coordinator: SunSynkCoordinator,
    plant_id: int,
) -> list[Any]:
    """Get the charges list from plant detail data."""
    detail = get_plant_detail(coordinator, plant_id)
    if not detail:
        return []
    return getattr(detail, "charges", None) or []


def to_charge_type(value: Any) -> Any:
    """Convert a charge type value to the correct type for PlantIncomeCharge.

    The API uses a oneOf schema: type 1 = string "1", type 2 = integer 2, type 3 = string "3".
    """
    int_val = int(value) if value is not None else 1
    return int_val if int_val == 2 else str(int_val)


def build_income_charges(
    current_charges: list[Any],
    slot: int,
    *,
    price: str | None = None,
    start_range: str | None = None,
    end_range: str | None = None,
) -> list[Any]:
    """Build a PlantIncomeCharge list from current charges with one slot overridden.

    Returns a list of PlantIncomeCharge objects ready for the set_plant_income_async call.
    """
    from sunsynk_api_client.models import PlantIncomeCharge

    result: list[PlantIncomeCharge] = []
    for i, charge in enumerate(current_charges):
        charge_type = getattr(charge, "type", None)
        c_price = price if i == slot and price is not None else str(getattr(charge, "price", 0))
        c_start = start_range if i == slot and start_range is not None else getattr(charge, "start_range", None)
        c_end = end_range if i == slot and end_range is not None else getattr(charge, "end_range", None)
        result.append(
            PlantIncomeCharge(
                price=c_price,
                type=to_charge_type(charge_type),
                start_range=c_start,
                end_range=c_end,
            )
        )
    return result


def get_plant_income_params(
    coordinator: SunSynkCoordinator,
    plant_id: int,
) -> tuple[int, float]:
    """Get currency ID and invest amount from plant detail."""
    detail = get_plant_detail(coordinator, plant_id)
    currency_id = 0
    invest = 0.0
    if detail:
        currency = getattr(detail, "currency", None)
        if currency:
            currency_id = getattr(currency, "id", 0) or 0
        invest = float(getattr(detail, "invest", 0) or 0)
    return currency_id, invest


def plant_device_info(coordinator: SunSynkCoordinator, plant_id: int) -> DeviceInfo:
    """Return DeviceInfo for a plant."""
    plant_info = coordinator.data.get("plants", {}).get(plant_id, {}).get("info") if coordinator.data else None
    plant_name = getattr(plant_info, "name", None) or f"Plant {plant_id}"
    return DeviceInfo(
        identifiers={(DOMAIN, f"plant_{plant_id}")},
        name=f"SunSynk {plant_name}",
        manufacturer="SunSynk",
        model="Solar Plant",
    )


def inverter_device_info(plant_id: int, sn: str) -> DeviceInfo:
    """Return DeviceInfo for an inverter."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"inverter_{sn}")},
        name=f"SunSynk Inverter {sn}",
        manufacturer="SunSynk",
        model="Inverter",
        serial_number=sn,
        via_device=(DOMAIN, f"plant_{plant_id}"),
    )
