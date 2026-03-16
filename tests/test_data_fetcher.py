"""Tests for data_fetcher module."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from custom_components.sunsynk.const import SunSynkApiError, SunSynkAuthError
from custom_components.sunsynk.data_fetcher import (
    ErrorTracker,
    TokenManager,
    _fetch_successful,
    fetch_all_data_sync,
    write_settings_sync,
)


class TestErrorTracker:
    """Tests for ErrorTracker."""

    def test_initial_state(self) -> None:
        tracker = ErrorTracker()
        errors = tracker.as_dict()
        for cat in ("Bearer", "Events", "Updates", "Flow", "InvList", "InvParam"):
            assert errors[cat]["count"] == 0
            assert errors[cat]["payload"] == ""
            assert errors[cat]["date"] == ""

    def test_record_increments_count(self) -> None:
        tracker = ErrorTracker()
        tracker.record("Bearer", Exception("auth failed"))
        errors = tracker.as_dict()
        assert errors["Bearer"]["count"] == 1
        assert errors["Bearer"]["payload"] == "auth failed"
        assert errors["Bearer"]["date"] != ""

    def test_record_multiple(self) -> None:
        tracker = ErrorTracker()
        tracker.record("Events", Exception("timeout"))
        tracker.record("Events", Exception("bad response"))
        errors = tracker.as_dict()
        assert errors["Events"]["count"] == 2
        assert errors["Events"]["payload"] == "bad response"

    def test_record_unknown_category_ignored(self) -> None:
        tracker = ErrorTracker()
        tracker.record("Unknown", Exception("test"))
        errors = tracker.as_dict()
        assert "Unknown" not in errors

    def test_payload_truncated_to_16_chars(self) -> None:
        tracker = ErrorTracker()
        tracker.record("Bearer", Exception("a" * 100))
        errors = tracker.as_dict()
        assert len(errors["Bearer"]["payload"]) == 16


class TestTokenManager:
    """Tests for TokenManager."""

    @patch("custom_components.sunsynk.data_fetcher.authenticate")
    def test_get_token_authenticates(self, mock_auth: MagicMock) -> None:
        mock_auth.return_value = MagicMock(
            access_token="test_token",
            token_type="bearer",
            expires_in=3600,
        )
        tm = TokenManager("test@example.com", "password", 0)
        token = tm.get_token()
        assert token == "test_token"
        mock_auth.assert_called_once_with("test@example.com", "password", 0)

    @patch("custom_components.sunsynk.data_fetcher.authenticate")
    def test_get_token_caches(self, mock_auth: MagicMock) -> None:
        mock_auth.return_value = MagicMock(
            access_token="test_token",
            token_type="bearer",
            expires_in=3600,
        )
        tm = TokenManager("test@example.com", "password", 0)
        tm.get_token()
        tm.get_token()
        assert mock_auth.call_count == 1


class TestWriteSettingsSync:
    """Tests for write_settings_sync."""

    @patch("custom_components.sunsynk.data_fetcher.authenticate")
    @patch("custom_components.sunsynk.data_fetcher.SunSynk")
    def test_write_settings_calls_api(
        self, mock_client_cls: MagicMock, mock_auth: MagicMock,
    ) -> None:
        mock_auth.return_value = MagicMock(
            access_token="tok", token_type="bearer", expires_in=3600,
        )
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.settings.write_inverter_settings.return_value = MagicMock(
            code=0, msg="success",
        )

        tm = TokenManager("test@example.com", "pass", 0)
        result = write_settings_sync(tm, 0, "SN123", {"cap1": "50"})

        mock_client.settings.write_inverter_settings.assert_called_once()
        call_kwargs = mock_client.settings.write_inverter_settings.call_args.kwargs
        assert call_kwargs["sn"] == "SN123"
        assert result["code"] == 0
        assert result["msg"] == "success"

    @patch("custom_components.sunsynk.data_fetcher.authenticate")
    @patch("custom_components.sunsynk.data_fetcher.SunSynk")
    def test_write_settings_tracks_error(
        self, mock_client_cls: MagicMock, mock_auth: MagicMock,
    ) -> None:
        mock_auth.return_value = MagicMock(
            access_token="tok", token_type="bearer", expires_in=3600,
        )
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.settings.write_inverter_settings.side_effect = RuntimeError("fail")

        tm = TokenManager("test@example.com", "pass", 0)
        tracker = ErrorTracker()
        with pytest.raises(RuntimeError):
            write_settings_sync(tm, 0, "SN123", {"cap1": "50"}, tracker)

        assert tracker.as_dict()["Updates"]["count"] == 1


class TestTokenManagerExpiry:
    """Tests for token expiry logic."""

    @patch("custom_components.sunsynk.data_fetcher.authenticate")
    def test_token_refreshes_when_expired(self, mock_auth: MagicMock) -> None:
        """Token should be re-fetched when it expires."""
        mock_auth.return_value = MagicMock(
            access_token="token1",
            token_type="bearer",
            expires_in=1,  # 1 second, less than 60s buffer
        )
        tm = TokenManager("test@example.com", "password", 0)
        tm.get_token()
        # Token is already "expired" because expires_in(1) - buffer(60) < 0
        tm.get_token()
        assert mock_auth.call_count == 2

    @patch("custom_components.sunsynk.data_fetcher.authenticate")
    def test_token_auth_error_propagates(self, mock_auth: MagicMock) -> None:
        """Auth errors should propagate from get_token."""
        mock_auth.side_effect = SunSynkAuthError("bad creds")
        tm = TokenManager("test@example.com", "password", 0)
        with pytest.raises(SunSynkAuthError):
            tm.get_token()


class TestFetchSuccessful:
    """Tests for the _fetch_successful helper."""

    def test_returns_data_on_success(self) -> None:
        mock_response = MagicMock(success=True, data="result_data")
        result = _fetch_successful(lambda: mock_response)
        assert result == "result_data"

    def test_returns_none_on_failure(self) -> None:
        mock_response = MagicMock(success=False)
        result = _fetch_successful(lambda: mock_response)
        assert result is None

    def test_returns_none_on_exception(self) -> None:
        def raise_error():
            raise RuntimeError("network error")
        result = _fetch_successful(raise_error)
        assert result is None

    def test_tracks_error_on_exception(self) -> None:
        tracker = ErrorTracker()
        def raise_error():
            raise RuntimeError("fail")
        _fetch_successful(raise_error, tracker, "Flow")
        assert tracker.as_dict()["Flow"]["count"] == 1

    def test_returns_none_for_none_response(self) -> None:
        result = _fetch_successful(lambda: None)
        assert result is None


class TestFetchAllDataSync:
    """Tests for fetch_all_data_sync."""

    @patch("custom_components.sunsynk.data_fetcher.authenticate")
    @patch("custom_components.sunsynk.data_fetcher.SunSynk")
    def test_auth_error_tracked_and_raised(
        self, mock_client_cls: MagicMock, mock_auth: MagicMock,
    ) -> None:
        """Auth errors during fetch should be tracked and re-raised."""
        mock_auth.side_effect = SunSynkAuthError("token expired")
        tm = TokenManager("test@example.com", "pass", 0)
        tracker = ErrorTracker()

        with pytest.raises(SunSynkAuthError):
            fetch_all_data_sync(tm, 0, tracker)

        assert tracker.as_dict()["Bearer"]["count"] == 1

    @patch("custom_components.sunsynk.data_fetcher.authenticate")
    @patch("custom_components.sunsynk.data_fetcher.SunSynk")
    def test_no_plants_raises_api_error(
        self, mock_client_cls: MagicMock, mock_auth: MagicMock,
    ) -> None:
        """Should raise SunSynkApiError when no plants are returned."""
        mock_auth.return_value = MagicMock(
            access_token="tok", token_type="bearer", expires_in=3600,
        )
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.plants.get_plants.return_value = MagicMock(
            success=False, data=None,
        )

        tm = TokenManager("test@example.com", "pass", 0)
        with pytest.raises(SunSynkApiError):
            fetch_all_data_sync(tm, 0)

    @patch("custom_components.sunsynk.data_fetcher.authenticate")
    @patch("custom_components.sunsynk.data_fetcher.SunSynk")
    def test_plant_ignore_list(
        self, mock_client_cls: MagicMock, mock_auth: MagicMock,
    ) -> None:
        """Plants in the ignore list should be skipped."""
        mock_auth.return_value = MagicMock(
            access_token="tok", token_type="bearer", expires_in=3600,
        )
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        plant1 = MagicMock(id=1, name="Plant 1")
        plant2 = MagicMock(id=2, name="Plant 2")
        mock_client.plants.get_plants.return_value = MagicMock(
            success=True, data=MagicMock(infos=[plant1, plant2]),
        )
        # Mock system data
        mock_client.gateways.get_gateways.return_value = MagicMock(
            success=True, data=MagicMock(infos=[]),
        )
        mock_client.events.get_events.return_value = MagicMock(
            success=False, data=None,
        )
        mock_client.notifications.get_messages.return_value = MagicMock(
            success=True, data=MagicMock(infos=[]),
        )
        # Mock plant data - return empty inverter list
        mock_client.plants.get_plant_flow.return_value = MagicMock(
            success=True, data=MagicMock(),
        )
        mock_client.inverters.get_plant_inverters.return_value = MagicMock(
            success=True, data=MagicMock(infos=[]),
        )

        tm = TokenManager("test@example.com", "pass", 0)
        result = fetch_all_data_sync(tm, 0, plant_ignore_list={"1"})

        # Plant 1 should be ignored, only plant 2 present
        assert 1 not in result["plants"]
        assert 2 in result["plants"]
