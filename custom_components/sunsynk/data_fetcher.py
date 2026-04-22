"""Standalone data fetching logic for SunSynk (no Home Assistant dependency)."""

from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime
from typing import Any

import httpx
from sunsynk_api_client import SunSynk
from sunsynk_api_client.models import InverterSettings, PlantIncomeCharge

from .auth import AuthResult, async_authenticate
from .const import SunSynkApiError

# Add TRACE level (below DEBUG=10)
TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def _trace(logger: logging.Logger, msg: str, *args: Any) -> None:
    if logger.isEnabledFor(TRACE):
        logger.log(TRACE, msg, *args)


_LOGGER = logging.getLogger(__name__)

# Error tracking categories matching Node-RED implementation
ERROR_CATEGORIES = ("Bearer", "Events", "Updates", "Flow", "InvList", "InvParam")


class ErrorTracker:
    """Track API errors by category."""

    def __init__(self) -> None:
        self._errors: dict[str, dict[str, Any]] = {
            cat: {"count": 0, "payload": "", "date": ""} for cat in ERROR_CATEGORIES
        }

    def record(self, category: str, error: Exception) -> None:
        """Record an error in the given category."""
        entry = self._errors.get(category)
        if entry is None:
            return
        entry["count"] += 1
        entry["payload"] = str(error)[:16]
        entry["date"] = datetime.now().isoformat()

    def as_dict(self) -> dict[str, dict[str, Any]]:
        """Return a copy of all error data."""
        return {k: dict(v) for k, v in self._errors.items()}


# Buffer in seconds before token expiry to trigger re-authentication
_TOKEN_EXPIRY_BUFFER = 60


class TokenManager:
    """Manages caching and refreshing of SunSynk auth tokens."""

    def __init__(
        self,
        email: str,
        password: str,
        region_idx: int,
        async_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialise the token manager."""
        _LOGGER.debug("TokenManager init: email=%s region_idx=%d", email, region_idx)
        self._email = email
        self._password = password
        self._region_idx = region_idx
        self._async_client = async_client
        self._auth_result: AuthResult | None = None
        self._token_obtained_at: float = 0

    async def async_get_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        expired = self._is_token_expired()
        _LOGGER.debug(
            "async_get_token: auth_result_present=%s expired=%s",
            self._auth_result is not None,
            expired,
        )
        if self._auth_result is None or expired:
            _LOGGER.debug("Obtaining new SunSynk auth token")
            self._auth_result = await async_authenticate(
                self._email, self._password, self._region_idx, self._async_client
            )
            self._token_obtained_at = time.monotonic()
            _LOGGER.debug(
                "Token obtained: token_type=%s expires_in=%d",
                self._auth_result.token_type,
                self._auth_result.expires_in,
            )
            _trace(_LOGGER, "Token value: %s", self._auth_result.access_token)
        return self._auth_result.access_token

    def _is_token_expired(self) -> bool:
        """Check if the cached token has expired (with buffer)."""
        if self._auth_result is None:
            return True
        elapsed = time.monotonic() - self._token_obtained_at
        threshold = self._auth_result.expires_in - _TOKEN_EXPIRY_BUFFER
        expired = elapsed >= threshold
        _LOGGER.debug(
            "_is_token_expired: elapsed=%.1fs threshold=%.1fs expired=%s",
            elapsed,
            threshold,
            expired,
        )
        return expired


async def _async_fetch_successful(
    fetch_coro: Any,
    error_tracker: ErrorTracker | None = None,
    error_category: str | None = None,
) -> Any | None:
    """Await a fetch coroutine and return its data if successful."""
    try:
        res = await fetch_coro
    except Exception as err:
        _LOGGER.debug("_async_fetch_successful: exception: %s", err)
        if error_tracker and error_category:
            error_tracker.record(error_category, err)
        return None
    _LOGGER.debug(
        "_async_fetch_successful: success=%s",
        res.success if res else None,
    )
    if res and res.success:
        _trace(_LOGGER, "_async_fetch_successful data: %s", res.data)
        return res.data
    if res and not res.success:
        _LOGGER.debug("_async_fetch_successful: non-success response: %s", res)
    return None


async def _async_fetch_inverter_data(client: SunSynk, sn: str, error_tracker: ErrorTracker) -> dict[str, Any]:
    """Fetch all realtime data for a single inverter."""
    _LOGGER.debug("_async_fetch_inverter_data: sn=%s", sn)
    fetchers: list[tuple[str, Any]] = [
        ("output", client.inverter_data.get_inverter_output_async(sn=sn)),
        ("input", client.inverter_data.get_inverter_input_async(sn=sn)),
        ("battery", client.inverter_data.get_battery_realtime_async(sn=sn)),
        ("grid", client.inverter_data.get_grid_realtime_async(sn=sn)),
        ("load", client.inverter_data.get_load_realtime_async(sn=sn)),
        ("gen", client.inverter_data.get_gen_realtime_async(sn=sn)),
        ("settings", client.settings.read_inverter_settings_async(sn=sn)),
        (
            "temp",
            client.inverter_data.get_inverter_daily_output_async(
                sn=sn,
                date_=date.today(),
                column="dc_temp,igbt_temp",
            ),
        ),
    ]

    result: dict[str, Any] = {}
    for key, coro in fetchers:
        _LOGGER.debug("Fetching inverter data: sn=%s key=%s", sn, key)
        data = await _async_fetch_successful(coro, error_tracker, "InvParam")
        result[key] = data
        _trace(_LOGGER, "Inverter %s[%s]: %s", sn, key, data)

    return result


async def _async_fetch_system_data(client: SunSynk, error_tracker: ErrorTracker) -> dict[str, Any]:
    """Fetch gateways, events, and notifications."""
    _LOGGER.debug("_async_fetch_system_data: start")
    data: dict[str, Any] = {
        "gateways": [],
        "events": {},
        "notifications": [],
    }

    _LOGGER.debug("Fetching gateways")
    gateways_res = await _async_fetch_successful(client.gateways.get_gateways_async())
    if gateways_res:
        data["gateways"] = gateways_res.infos
        _LOGGER.debug("Gateways found: %d", len(gateways_res.infos))
        _trace(_LOGGER, "Gateways: %s", gateways_res.infos)

    for event_type in [1, 2, 3]:
        _LOGGER.debug("Fetching events: type=%d", event_type)
        try:
            events_res = await client.events.get_events_async(type_=event_type)
        except Exception as err:
            _LOGGER.debug("Events type=%d fetch error: %s", event_type, err)
            error_tracker.record("Events", err)
            continue
        _LOGGER.debug(
            "Events type=%d: success=%s has_data=%s",
            event_type,
            events_res.success if events_res else None,
            bool(events_res and events_res.data) if events_res else False,
        )
        if events_res and events_res.success and events_res.data:
            data["events"][event_type] = events_res.data.record
            _trace(_LOGGER, "Events type=%d: %s", event_type, events_res.data.record)

    _LOGGER.debug("Fetching notifications")
    msgs_res = await _async_fetch_successful(client.notifications.get_messages_async(), error_tracker, "Events")
    if msgs_res:
        data["notifications"] = msgs_res.infos
        _LOGGER.debug("Notifications found: %d", len(msgs_res.infos))
        _trace(_LOGGER, "Notifications: %s", msgs_res.infos)

    return data


async def _async_fetch_plant_data(client: SunSynk, plant: Any, error_tracker: ErrorTracker) -> dict[str, Any]:
    """Fetch flow and inverter data for a single plant."""
    plant_id = str(plant.id)
    plant_name = getattr(plant, "name", plant_id)
    _LOGGER.debug("_async_fetch_plant_data: plant_id=%s name=%s", plant_id, plant_name)
    _trace(_LOGGER, "Plant object: %s", plant)

    plant_data: dict[str, Any] = {
        "info": plant,
        "detail": None,
        "flow": None,
        "inverters": {},
    }

    _LOGGER.debug("Fetching plant detail: plant_id=%s", plant_id)
    plant_data["detail"] = await _async_fetch_successful(
        client.plants.get_plant_async(plant_id=plant_id),
        error_tracker,
        "Flow",
    )
    _LOGGER.debug("Plant detail fetched: plant_id=%s has_detail=%s", plant_id, plant_data["detail"] is not None)
    _trace(_LOGGER, "Plant detail: %s", plant_data["detail"])

    _LOGGER.debug("Fetching plant flow: plant_id=%s", plant_id)
    plant_data["flow"] = await _async_fetch_successful(
        client.plants.get_plant_flow_async(plant_id=plant_id),
        error_tracker,
        "Flow",
    )
    _LOGGER.debug("Plant flow fetched: plant_id=%s has_flow=%s", plant_id, plant_data["flow"] is not None)
    _trace(_LOGGER, "Plant flow: %s", plant_data["flow"])

    _LOGGER.debug("Fetching inverters for plant_id=%s", plant_id)
    try:
        inv_res = await client.inverters.get_plant_inverters_async(plant_id=plant_id)
    except Exception as err:
        _LOGGER.exception("Error fetching inverter list for plant %s", plant_id)
        error_tracker.record("InvList", err)
        return plant_data
    _LOGGER.debug(
        "Inverters response: plant_id=%s success=%s",
        plant_id,
        inv_res.success if inv_res else None,
    )

    if not inv_res or not inv_res.success or not inv_res.data:
        _LOGGER.debug("No inverters found for plant_id=%s", plant_id)
        return plant_data

    inverter_list = inv_res.data.infos or []
    _LOGGER.debug("Inverters found: plant_id=%s count=%d", plant_id, len(inverter_list))
    _trace(_LOGGER, "Inverter list: %s", inverter_list)

    for inv in inverter_list:
        if not inv.sn:
            _LOGGER.debug("Skipping inverter with no serial number")
            continue
        _LOGGER.debug("Processing inverter: sn=%s", inv.sn)
        try:
            inv_data = await _async_fetch_inverter_data(client, inv.sn, error_tracker)
        except Exception:
            _LOGGER.exception("Error fetching data for inverter %s", inv.sn)
            error_tracker.record("InvParam", Exception(f"inverter {inv.sn}"))
            inv_data = {}
        inv_data["info"] = inv
        _trace(_LOGGER, "Inverter %s info: %s", inv.sn, inv)
        plant_data["inverters"][inv.sn] = inv_data

    return plant_data


async def async_fetch_all_data(
    token_manager: TokenManager,
    region_idx: int,
    error_tracker: ErrorTracker | None = None,
    plant_ignore_list: set[str] | None = None,
    async_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Fetch all data from SunSynk asynchronously."""
    _LOGGER.debug("async_fetch_all_data: region_idx=%d", region_idx)

    if error_tracker is None:
        error_tracker = ErrorTracker()

    try:
        token = await token_manager.async_get_token()
    except Exception as err:
        error_tracker.record("Bearer", err)
        raise

    async with SunSynk(
        bearer_auth=token,
        server_idx=region_idx,
        async_client=async_client,
    ) as client:
        _LOGGER.debug("SunSynk client created, fetching plants")
        plants_res = await client.plants.get_plants_async()
        _LOGGER.debug(
            "Plants response: success=%s",
            plants_res.success if plants_res else None,
        )

        if not plants_res or not plants_res.success or not plants_res.data:
            raise SunSynkApiError("Failed to fetch plants from SunSynk")

        plant_list = plants_res.data.infos or []
        _LOGGER.debug("Plants found: count=%d", len(plant_list))
        _trace(_LOGGER, "Plant list: %s", plant_list)

        data = await _async_fetch_system_data(client, error_tracker)
        data["plants"] = {}
        for plant in plant_list:
            plant_id_str = str(plant.id)
            if plant_ignore_list and plant_id_str in plant_ignore_list:
                _LOGGER.debug("Skipping ignored plant: id=%s name=%s", plant.id, getattr(plant, "name", "?"))
                continue
            _LOGGER.debug("Processing plant: id=%s name=%s", plant.id, getattr(plant, "name", "?"))
            data["plants"][plant.id] = await _async_fetch_plant_data(client, plant, error_tracker)

    data["errors"] = error_tracker.as_dict()
    data["last_update"] = datetime.now(tz=UTC)

    _LOGGER.debug(
        "async_fetch_all_data complete: plants=%d gateways=%d notifications=%d",
        len(plant_list),
        len(data["gateways"]),
        len(data["notifications"]),
    )
    return data


# camelCase API keys → snake_case kwargs for set_inverter_settings_async
_API_KEY_TO_SNAKE: dict[str, str] = {
    "sellTime1": "sell_time1",
    "sellTime2": "sell_time2",
    "sellTime3": "sell_time3",
    "sellTime4": "sell_time4",
    "sellTime5": "sell_time5",
    "sellTime6": "sell_time6",
    "cap1": "cap1",
    "cap2": "cap2",
    "cap3": "cap3",
    "cap4": "cap4",
    "cap5": "cap5",
    "cap6": "cap6",
    "time1on": "time1on",
    "time2on": "time2on",
    "time3on": "time3on",
    "time4on": "time4on",
    "time5on": "time5on",
    "time6on": "time6on",
    "genTime1on": "gen_time1on",
    "genTime2on": "gen_time2on",
    "genTime3on": "gen_time3on",
    "genTime4on": "gen_time4on",
    "genTime5on": "gen_time5on",
    "genTime6on": "gen_time6on",
    "sellTime1on": "sell_time1on",
    "sellTime2on": "sell_time2on",
    "sellTime3on": "sell_time3on",
    "sellTime4on": "sell_time4on",
    "sellTime5on": "sell_time5on",
    "sellTime6on": "sell_time6on",
    "peakAndVallery": "peak_and_vallery",
    "energyMode": "energy_mode",
    "sysWorkMode": "sys_work_mode",
    "batteryRestartCap": "battery_restart_cap",
    "batteryShutdownCap": "battery_shutdown_cap",
    "batteryMaxCurrentCharge": "battery_max_current_charge",
    "batteryMaxCurrentDischarge": "battery_max_current_discharge",
    "batteryLowCap": "battery_low_cap",
    "zeroExportPower": "zero_export_power",
    "solarSell": "solar_sell",
    "pvMaxLimit": "pv_max_limit",
    "sellTime1Pac": "sell_time1_pac",
    "sellTime2Pac": "sell_time2_pac",
    "sellTime3Pac": "sell_time3_pac",
    "sellTime4Pac": "sell_time4_pac",
    "sellTime5Pac": "sell_time5_pac",
    "sellTime6Pac": "sell_time6_pac",
    "sellTime1Volt": "sell_time1_volt",
    "sellTime2Volt": "sell_time2_volt",
    "sellTime3Volt": "sell_time3_volt",
    "sellTime4Volt": "sell_time4_volt",
    "sellTime5Volt": "sell_time5_volt",
    "sellTime6Volt": "sell_time6_volt",
}

# Minimum required fields for the set endpoint (snake_case names matching InverterSettings attrs).
#
# The SunSynk portal sends the full programme state on every write. Submitting
# a single toggle (e.g. time1on) without the accompanying per-slot power and
# voltage values — plus system-level mode flags — causes the server to
# silently drop the change and reply with the prior state, which manifests in
# HA as a switch flipping back a few seconds after toggling.
#
# See setrequest.json for a captured portal payload.
_MIN_REQUIRED_FIELDS: list[str] = [
    # Programme times (per slot)
    "sell_time1",
    "sell_time2",
    "sell_time3",
    "sell_time4",
    "sell_time5",
    "sell_time6",
    # Programme SOC caps (per slot)
    "cap1",
    "cap2",
    "cap3",
    "cap4",
    "cap5",
    "cap6",
    # Programme output power (per slot)
    "sell_time1_pac",
    "sell_time2_pac",
    "sell_time3_pac",
    "sell_time4_pac",
    "sell_time5_pac",
    "sell_time6_pac",
    # Programme voltage floor (per slot)
    "sell_time1_volt",
    "sell_time2_volt",
    "sell_time3_volt",
    "sell_time4_volt",
    "sell_time5_volt",
    "sell_time6_volt",
    # Per-slot on flags
    "time1on",
    "time2on",
    "time3on",
    "time4on",
    "time5on",
    "time6on",
    "gen_time1on",
    "gen_time2on",
    "gen_time3on",
    "gen_time4on",
    "gen_time5on",
    "gen_time6on",
    "sell_time1on",
    "sell_time2on",
    "sell_time3on",
    "sell_time4on",
    "sell_time5on",
    "sell_time6on",
    # System-level flags that gate timer programme acceptance
    "solar_sell",
    "pv_max_limit",
    "peak_and_vallery",
    "sys_work_mode",
]


def _build_set_kwargs(
    settings: dict[str, str],
    current_settings: InverterSettings | None,
) -> dict[str, Any]:
    """Build kwargs for set_inverter_settings_async from camelCase settings dict.

    Merges user changes with minimum required fields from current inverter settings.
    """
    # Start with minimum required fields from current settings
    kwargs: dict[str, Any] = {}
    if current_settings is not None:
        for field_name in _MIN_REQUIRED_FIELDS:
            val = getattr(current_settings, field_name, None)
            if val is not None:
                kwargs[field_name] = val

    # Overlay user's changes (converting camelCase keys to snake_case)
    for api_key, value in settings.items():
        snake_key = _API_KEY_TO_SNAKE.get(api_key, api_key)
        kwargs[snake_key] = value

    return kwargs


async def async_write_settings(
    token_manager: TokenManager,
    region_idx: int,
    sn: str,
    settings: dict[str, str],
    current_settings: InverterSettings | None = None,
    error_tracker: ErrorTracker | None = None,
    async_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Write settings to an inverter asynchronously. Returns response dict with code/msg."""
    _LOGGER.debug("async_write_settings: sn=%s settings=%s", sn, settings)

    if error_tracker is None:
        error_tracker = ErrorTracker()

    try:
        token = await token_manager.async_get_token()
    except Exception as err:
        error_tracker.record("Bearer", err)
        raise

    kwargs = _build_set_kwargs(settings, current_settings)
    _LOGGER.debug("async_write_settings: resolved kwargs=%s", kwargs)

    async with SunSynk(
        bearer_auth=token,
        server_idx=region_idx,
        async_client=async_client,
    ) as client:
        try:
            resp = await client.settings.set_inverter_settings_async(
                sn_param=sn,
                **kwargs,
            )
        except Exception as err:
            _LOGGER.exception("Error writing settings for inverter %s", sn)
            error_tracker.record("Updates", err)
            raise

    code = getattr(resp, "code", None)
    msg = getattr(resp, "msg", None)
    _LOGGER.debug("async_write_settings result: code=%s msg=%s", code, msg)
    return {"code": code, "msg": msg}


async def async_set_plant_income(
    token_manager: TokenManager,
    region_idx: int,
    plant_id: str,
    currency: int,
    invest: float,
    charges: list[PlantIncomeCharge],
    error_tracker: ErrorTracker | None = None,
    async_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Set plant income pricing. Returns response dict with code/msg."""
    _LOGGER.debug("async_set_plant_income: plant_id=%s charges=%s", plant_id, charges)

    if error_tracker is None:
        error_tracker = ErrorTracker()

    try:
        token = await token_manager.async_get_token()
    except Exception as err:
        error_tracker.record("Bearer", err)
        raise

    async with SunSynk(
        bearer_auth=token,
        server_idx=region_idx,
        async_client=async_client,
    ) as client:
        try:
            resp = await client.plants.set_plant_income_async(
                plant_id=plant_id,
                id=plant_id,
                currency=currency,
                invest=invest,
                charges=charges,
            )
        except Exception as err:
            _LOGGER.exception("Error setting plant income for plant %s", plant_id)
            error_tracker.record("Updates", err)
            raise

    code = getattr(resp, "code", None)
    msg = getattr(resp, "msg", None)
    _LOGGER.debug("async_set_plant_income result: code=%s msg=%s", code, msg)
    return {"code": code, "msg": msg}
