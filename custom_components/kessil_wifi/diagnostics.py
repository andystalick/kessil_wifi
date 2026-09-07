"""Diagnostics support for the Kessil WiFi integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import KessilConfigEntry

# The dongle reports the home WiFi SSID; the serial is the device identifier.
TO_REDACT = {CONF_HOST, "ssid", "serial"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: KessilConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    device = coordinator.device_info

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "device_info": async_redact_data(asdict(device), TO_REDACT) if device else None,
        "group_state": asdict(coordinator.data) if coordinator.data else None,
    }
