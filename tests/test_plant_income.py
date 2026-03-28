"""Tests for plant income/charge entities (sensors, numbers, selects)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sunsynk.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REGION,
    DOMAIN,
)
from custom_components.sunsynk.data_fetcher import (
    ErrorTracker,
    TokenManager,
    async_set_plant_income,
)
from custom_components.sunsynk.helpers import build_income_charges

VALID_CONFIG = {
    CONF_REGION: 0,
    CONF_EMAIL: "test@example.com",
    CONF_PASSWORD: "secret123",
}


def _make_charge(price=27.0, charge_type=1, start="00:00", end="24:00"):
    return SimpleNamespace(
        id=1, price=price, type=charge_type,
        start_range=start, end_range=end,
        station_id=1, create_at=None, status="import",
    )


def _make_coordinator_data(charges=None):
    if charges is None:
        charges = [_make_charge()]
    return {
        "plants": {
            1: {
                "info": SimpleNamespace(id=1, name="Plant"),
                "detail": SimpleNamespace(
                    charges=charges,
                    currency=SimpleNamespace(id=366, code="GBP", text="British Pound"),
                    invest=5000.0,
                ),
                "flow": SimpleNamespace(
                    pvPower=0, battPower=0, gridOrMeterPower=0,
                    loadOrEpsPower=0, soc=75, genPower=0,
                    minPower=0, smartLoadPower=0, homeLoadPower=0, upsLoadPower=0,
                ),
                "inverters": {
                    "SN001": {
                        "info": SimpleNamespace(sn="SN001"),
                        "output": SimpleNamespace(pac=0, fac=50, vip=[]),
                        "input": SimpleNamespace(pvPower=0, eToday=0, eTotal=0, pvIV=[]),
                        "battery": SimpleNamespace(
                            soc=75, voltage=52, chargeVolt=56, status="idle",
                            chargeCurrentLimit=100, dischargeCurrentLimit=100,
                            capacity=10000, current=0, power=0,
                            etotalChg=0, etotalDischg=0, eDayChg=0, eDayDischg=0,
                            bmsTemperature=25,
                        ),
                        "grid": SimpleNamespace(
                            power=0, fac=50, status=1, powerFactor=1,
                            etotalTo=0, etotalFrom=0, eDayTo=0, eDayFrom=0,
                            limiterTotalPower=0, vip=[],
                        ),
                        "load": SimpleNamespace(
                            totalPower=0, totalUsed=0, dailyUsed=0, fac=50,
                            smartLoadStatus="off", upsPower=0, vip=[],
                        ),
                        "gen": SimpleNamespace(
                            etotalGen=0, eDayGen=0, genPower=0, fac=0,
                            vip=[],
                        ),
                        "settings": SimpleNamespace(
                            sell_time1="00:00", sell_time2="06:00",
                            sell_time3="12:00", sell_time4="18:00",
                            sell_time5="00:00", sell_time6="00:00",
                            cap1=20, cap2=30, cap3=40, cap4=50, cap5=60, cap6=70,
                            time1on="1", time2on="0", time3on="0",
                            time4on="0", time5on="0", time6on="0",
                            gen_time1on="0", gen_time2on="0", gen_time3on="0",
                            gen_time4on="0", gen_time5on="0", gen_time6on="0",
                            peak_and_vallery="1", energy_mode="0", sys_work_mode="1",
                            sell_time1_pac=5000, sell_time2_pac=5000,
                            sell_time3_pac=5000, sell_time4_pac=5000,
                            sell_time5_pac=5000, sell_time6_pac=5000,
                            battery_restart_cap=15, battery_shutdown_cap=10,
                            battery_max_current_charge=100,
                        ),
                        "temp": SimpleNamespace(infos=[]),
                    },
                },
            },
        },
        "gateways": [],
        "events": {},
        "notifications": [],
        "errors": {
            "Bearer": {"count": 0, "payload": "", "date": ""},
            "Events": {"count": 0, "payload": "", "date": ""},
            "Updates": {"count": 0, "payload": "", "date": ""},
            "Flow": {"count": 0, "payload": "", "date": ""},
            "InvList": {"count": 0, "payload": "", "date": ""},
            "InvParam": {"count": 0, "payload": "", "date": ""},
        },
        "last_update": datetime(2025, 1, 1, tzinfo=UTC),
    }


@pytest.fixture
async def setup_integration(hass: HomeAssistant):
    """Set up the integration with mock data including charges."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test@example.com",
        data=VALID_CONFIG,
        options={},
    )
    entry.add_to_hass(hass)

    with (
        patch("custom_components.sunsynk.TokenManager"),
        patch(
            "custom_components.sunsynk.async_fetch_all_data",
            return_value=_make_coordinator_data(),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    return entry


# ---------------------------------------------------------------------------
# Sensor tests
# ---------------------------------------------------------------------------


async def test_charge_sensor_created(hass: HomeAssistant, setup_integration) -> None:
    """Test that charge sensor entities are created."""
    entity_reg = er.async_get(hass)
    charge_sensors = [
        e for e in entity_reg.entities.values()
        if e.platform == "sunsynk" and e.domain == "sensor" and "plant_1_charge_" in e.unique_id
    ]
    assert len(charge_sensors) == 1  # one charge slot


async def test_charge_sensor_registered(hass: HomeAssistant, setup_integration) -> None:
    """Test charge sensor entity is properly registered."""
    entity_reg = er.async_get(hass)
    entity = entity_reg.async_get("sensor.sunsynk_plant_charge_slot_1")
    assert entity is not None
    assert entity.unique_id == "sunsynk_plant_1_charge_0"


# ---------------------------------------------------------------------------
# Number tests
# ---------------------------------------------------------------------------


async def test_charge_price_number_created(hass: HomeAssistant, setup_integration) -> None:
    """Test that charge price number entities are created."""
    entity_reg = er.async_get(hass)
    charge_numbers = [
        e for e in entity_reg.entities.values()
        if e.platform == "sunsynk" and e.domain == "number" and "charge_price" in e.unique_id
    ]
    assert len(charge_numbers) == 1


async def test_charge_price_set_value(hass: HomeAssistant, setup_integration) -> None:
    """Test setting a charge price calls async_set_plant_income."""
    entity_reg = er.async_get(hass)
    price_entities = [
        e for e in entity_reg.entities.values()
        if e.platform == "sunsynk" and e.domain == "number" and "charge_price" in e.unique_id
    ]
    assert len(price_entities) == 1
    entity_id = price_entities[0].entity_id

    with (
        patch(
            "custom_components.sunsynk.number.async_set_plant_income",
        ) as mock_set,
        patch(
            "custom_components.sunsynk.async_fetch_all_data",
            return_value=_make_coordinator_data(),
        ),
    ):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id, "value": 35.5},
            blocking=True,
        )

    mock_set.assert_called_once()
    call_args = mock_set.call_args
    # positional: token_manager, region_idx, plant_id, currency, invest, charges
    assert call_args[0][2] == "1"  # plant_id
    assert call_args[0][3] == 366  # currency
    assert call_args[0][4] == 5000.0  # invest
    charges = call_args[0][5]
    assert len(charges) == 1
    assert charges[0].price == "35.5"


# ---------------------------------------------------------------------------
# Select tests
# ---------------------------------------------------------------------------


async def test_pricing_type_select_created(hass: HomeAssistant, setup_integration) -> None:
    """Test that pricing type select entity is created."""
    entity_reg = er.async_get(hass)
    pricing_selects = [
        e for e in entity_reg.entities.values()
        if e.platform == "sunsynk" and e.domain == "select" and "pricing_type" in e.unique_id
    ]
    assert len(pricing_selects) == 1


async def test_charge_time_selects_created(hass: HomeAssistant, setup_integration) -> None:
    """Test that charge time range select entities are created."""
    entity_reg = er.async_get(hass)
    time_selects = [
        e for e in entity_reg.entities.values()
        if e.platform == "sunsynk" and e.domain == "select" and "charge_" in e.unique_id
        and "pricing" not in e.unique_id
    ]
    # 1 charge slot * 2 (start + end) = 2
    assert len(time_selects) == 2


async def test_pricing_type_set(hass: HomeAssistant, setup_integration) -> None:
    """Test setting pricing type calls async_set_plant_income."""
    entity_reg = er.async_get(hass)
    pricing_entities = [
        e for e in entity_reg.entities.values()
        if e.platform == "sunsynk" and e.domain == "select" and "pricing_type" in e.unique_id
    ]
    assert len(pricing_entities) == 1
    entity_id = pricing_entities[0].entity_id

    with (
        patch(
            "custom_components.sunsynk.select.async_set_plant_income",
        ) as mock_set,
        patch(
            "custom_components.sunsynk.async_fetch_all_data",
            return_value=_make_coordinator_data(),
        ),
    ):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "2"},
            blocking=True,
        )

    mock_set.assert_called_once()
    charges = mock_set.call_args[0][5]  # positional arg: charges
    assert len(charges) >= 1
    assert charges[0].type == 2  # type 2 is integer per the API schema


async def test_charge_time_set(hass: HomeAssistant, setup_integration) -> None:
    """Test setting a charge time range calls async_set_plant_income."""
    entity_reg = er.async_get(hass)
    start_entities = [
        e for e in entity_reg.entities.values()
        if e.platform == "sunsynk" and e.domain == "select" and "charge_start" in e.unique_id
    ]
    assert len(start_entities) == 1
    entity_id = start_entities[0].entity_id

    with (
        patch(
            "custom_components.sunsynk.select.async_set_plant_income",
        ) as mock_set,
        patch(
            "custom_components.sunsynk.async_fetch_all_data",
            return_value=_make_coordinator_data(),
        ),
    ):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "06:00"},
            blocking=True,
        )

    mock_set.assert_called_once()
    charges = mock_set.call_args[0][5]  # positional arg: charges
    assert len(charges) == 1
    assert charges[0].start_range == "06:00"


# ---------------------------------------------------------------------------
# Multi-slot tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def setup_tou_integration(hass: HomeAssistant):
    """Set up with Time of Use (multiple charge slots)."""
    charges = [
        _make_charge(price=10, charge_type=2, start="00:00", end="07:00"),
        _make_charge(price=25, charge_type=2, start="07:00", end="19:00"),
        _make_charge(price=15, charge_type=2, start="19:00", end="24:00"),
    ]
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test@example.com",
        data=VALID_CONFIG,
        options={},
    )
    entry.add_to_hass(hass)

    with (
        patch("custom_components.sunsynk.TokenManager"),
        patch(
            "custom_components.sunsynk.async_fetch_all_data",
            return_value=_make_coordinator_data(charges),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    return entry


async def test_tou_multiple_charge_entities(hass: HomeAssistant, setup_tou_integration) -> None:
    """Test that multiple charge slots create multiple entities."""
    entity_reg = er.async_get(hass)
    charge_sensors = [
        e for e in entity_reg.entities.values()
        if e.platform == "sunsynk" and e.domain == "sensor" and "plant_1_charge_" in e.unique_id
    ]
    assert len(charge_sensors) == 3

    charge_numbers = [
        e for e in entity_reg.entities.values()
        if e.platform == "sunsynk" and e.domain == "number" and "plant_1_charge_price" in e.unique_id
    ]
    assert len(charge_numbers) == 3

    time_selects = [
        e for e in entity_reg.entities.values()
        if e.platform == "sunsynk" and e.domain == "select" and "plant_1_charge_" in e.unique_id
    ]
    # 3 slots * 2 (start + end) = 6
    assert len(time_selects) == 6


# ---------------------------------------------------------------------------
# data_fetcher tests
# ---------------------------------------------------------------------------


class TestSetPlantIncome:
    """Tests for async_set_plant_income."""

    @pytest.mark.asyncio
    @patch("custom_components.sunsynk.data_fetcher.async_authenticate", new_callable=AsyncMock)
    @patch("custom_components.sunsynk.data_fetcher.SunSynk")
    async def test_set_plant_income_calls_api(
        self, mock_client_cls, mock_auth,
    ) -> None:
        from sunsynk_api_client.models import PlantIncomeCharge

        mock_auth.return_value = SimpleNamespace(
            access_token="tok", token_type="bearer", expires_in=3600,
        )
        mock_client = SimpleNamespace()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_plants = SimpleNamespace()
        mock_plants.set_plant_income_async = AsyncMock(
            return_value=SimpleNamespace(code=0, msg="success"),
        )
        mock_client.plants = mock_plants

        charges = [PlantIncomeCharge(price="27", type="1", start_range="00:00", end_range="24:00")]

        tm = TokenManager("test@example.com", "pass", 0)
        result = await async_set_plant_income(tm, 0, "1", 366, 5000.0, charges)

        mock_plants.set_plant_income_async.assert_called_once()
        call_kwargs = mock_plants.set_plant_income_async.call_args.kwargs
        assert call_kwargs["plant_id"] == "1"
        assert call_kwargs["id"] == "1"
        assert call_kwargs["currency"] == 366
        assert call_kwargs["invest"] == 5000.0
        assert result["code"] == 0

    @pytest.mark.asyncio
    @patch("custom_components.sunsynk.data_fetcher.async_authenticate", new_callable=AsyncMock)
    @patch("custom_components.sunsynk.data_fetcher.SunSynk")
    async def test_set_plant_income_tracks_error(
        self, mock_client_cls, mock_auth,
    ) -> None:
        from sunsynk_api_client.models import PlantIncomeCharge

        mock_auth.return_value = SimpleNamespace(
            access_token="tok", token_type="bearer", expires_in=3600,
        )
        mock_client = SimpleNamespace()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_plants = SimpleNamespace()
        mock_plants.set_plant_income_async = AsyncMock(side_effect=RuntimeError("fail"))
        mock_client.plants = mock_plants

        charges = [PlantIncomeCharge(price="27", type="1", start_range="00:00", end_range="24:00")]

        tm = TokenManager("test@example.com", "pass", 0)
        tracker = ErrorTracker()
        with pytest.raises(RuntimeError):
            await async_set_plant_income(tm, 0, "1", 366, 5000.0, charges, error_tracker=tracker)

        assert tracker.as_dict()["Updates"]["count"] == 1


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestBuildIncomeCharges:
    """Tests for build_income_charges helper."""

    def test_override_price(self) -> None:
        charges = [_make_charge(price=10), _make_charge(price=20)]
        result = build_income_charges(charges, 0, price="50")
        assert result[0].price == "50"
        assert result[1].price == "20"

    def test_override_start_range(self) -> None:
        charges = [_make_charge()]
        result = build_income_charges(charges, 0, start_range="06:00")
        assert result[0].start_range == "06:00"
        assert result[0].end_range == "24:00"

    def test_override_end_range(self) -> None:
        charges = [_make_charge()]
        result = build_income_charges(charges, 0, end_range="12:00")
        assert result[0].start_range == "00:00"
        assert result[0].end_range == "12:00"

    def test_preserves_other_slots(self) -> None:
        charges = [
            _make_charge(price=10, start="00:00", end="12:00"),
            _make_charge(price=20, start="12:00", end="24:00"),
        ]
        result = build_income_charges(charges, 1, price="99")
        assert result[0].price == "10"
        assert result[0].start_range == "00:00"
        assert result[1].price == "99"
        assert result[1].start_range == "12:00"
