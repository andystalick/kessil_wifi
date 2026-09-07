"""Tests for setting up and tearing down the integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState


async def test_entry_loads(hass, setup_integration):
    assert setup_integration.state is ConfigEntryState.LOADED


async def test_entry_unloads(hass, setup_integration):
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()

    assert setup_integration.state is ConfigEntryState.NOT_LOADED


async def test_entry_retries_when_the_dongle_is_unreachable(hass, dongle, config_entry):
    dongle.fail_connections = True
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_device_is_registered_with_serial_and_firmware(hass, setup_integration):
    from homeassistant.helpers import device_registry as dr

    from custom_components.kessil_wifi.const import DOMAIN

    from .fake_dongle import DEFAULT_FIRMWARE, DEFAULT_SERIAL

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, DEFAULT_SERIAL)})

    assert device is not None
    assert device.sw_version == DEFAULT_FIRMWARE
    assert device.manufacturer == "Kessil"
