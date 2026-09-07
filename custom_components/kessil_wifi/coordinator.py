"""Polling coordinator for the Kessil WiFi integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DeviceInfo, GroupState, KessilAuthlessClient, KessilError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type KessilConfigEntry = ConfigEntry[KessilCoordinator]


class KessilCoordinator(DataUpdateCoordinator[GroupState]):
    """Polls one lamp group.

    The dongle has no push channel, so state is polled. Writes go through the
    same client, which serialises them against these polls.
    """

    config_entry: KessilConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: KessilConfigEntry,
        client: KessilAuthlessClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.device_info: DeviceInfo | None = None

    async def _async_setup(self) -> None:
        """Fetch dongle metadata once, before the first poll."""
        try:
            self.device_info = await self.client.async_get_device_info()
        except KessilError as err:
            raise UpdateFailed(f"Cannot reach Kessil dongle: {err}") from err

    async def _async_update_data(self) -> GroupState:
        try:
            return await self.client.async_get_state()
        except KessilError as err:
            raise UpdateFailed(f"Cannot read Kessil group state: {err}") from err
