"""Shared fixtures for the Kessil WiFi tests."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kessil_wifi.const import CONF_GID, DOMAIN

from .fake_dongle import DEFAULT_SERIAL, FakeDongle


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load the integration from custom_components/."""
    return


@pytest.fixture
async def dongle(socket_enabled):
    """A fake Kessil dongle listening on a loopback port.

    Needs ``socket_enabled`` because the Home Assistant test harness blocks
    real sockets, and these tests deliberately exercise the TCP client.
    """
    server = FakeDongle()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
def config_entry(dongle) -> MockConfigEntry:
    """A config entry pointing at the fake dongle."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"Kessil {DEFAULT_SERIAL}",
        unique_id=DEFAULT_SERIAL,
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: dongle.port,
            CONF_GID: dongle.gid,
        },
    )


@pytest.fixture
async def setup_integration(hass, config_entry):
    """Set the integration up against the fake dongle."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
