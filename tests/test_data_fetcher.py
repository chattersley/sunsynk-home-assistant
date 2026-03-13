"""Tests for data_fetcher module."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from custom_components.sunsynk.data_fetcher import (
    ErrorTracker,
    TokenManager,
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

        mock_client.settings.write_inverter_settings.assert_called_once_with(
            sn="SN123", body={"cap1": "50"},
        )
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
