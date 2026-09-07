"""The Kessil WiFi integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .api import KessilAuthlessClient
from .const import CONF_GID, DEFAULT_PORT
from .coordinator import KessilConfigEntry, KessilCoordinator

PLATFORMS: list[Platform] = [Platform.LIGHT]


async def async_setup_entry(hass: HomeAssistant, entry: KessilConfigEntry) -> bool:
    """Set up Kessil WiFi from a config entry."""
    client = KessilAuthlessClient(
        entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        gid=entry.data[CONF_GID],
    )
    coordinator = KessilCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KessilConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: KessilConfigEntry) -> None:
    """Reload when the entry's options or host change."""
    await hass.config_entries.async_reload(entry.entry_id)
