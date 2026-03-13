"""Local test script to fetch SunSynk data and print results."""

import json
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Allow running from the repo root without installing the package
sys.path.insert(0, os.path.dirname(__file__))

from custom_components.sunsynk.data_fetcher import ErrorTracker, TokenManager, fetch_all_data_sync  # noqa: E402


def _serialise(obj):
    """Fallback JSON serialiser for SDK model objects."""
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return repr(obj)


def main():
    email = os.environ.get("SUNSYNK_EMAIL")
    password = os.environ.get("SUNSYNK_PASSWORD")
    region_idx = int(os.environ.get("SUNSYNK_REGION", "0"))
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not email or not password:
        print(
            "Set SUNSYNK_EMAIL and SUNSYNK_PASSWORD environment variables before running.",
            file=sys.stderr,
        )
        sys.exit(1)

    token_manager = TokenManager(email, password, region_idx)
    error_tracker = ErrorTracker()

    print(f"Fetching data (region_idx={region_idx})…")
    data = fetch_all_data_sync(token_manager, region_idx, error_tracker)

    print(json.dumps(data, indent=2, default=_serialise))


if __name__ == "__main__":
    main()
