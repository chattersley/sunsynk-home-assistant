"""Constants for the SunSynk integration."""

try:
    from homeassistant.exceptions import HomeAssistantError
except ImportError:
    HomeAssistantError = Exception  # type: ignore[assignment,misc]

DOMAIN = "sunsynk_ha"


class SunSynkError(HomeAssistantError):
    """Base exception for SunSynk integration."""


class SunSynkAuthError(SunSynkError):
    """Error during authentication."""


class SunSynkApiError(SunSynkError):
    """Error communicating with the SunSynk API."""

CONF_REGION = "region"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"

REGIONS = {
    0: "Region 1 (Production - pv.inteless.com)",
    1: "Region 2 (Alternative - api.sunsynk.net)",
}
