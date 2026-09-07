"""Tests for the Kessil WiFi config flow."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType

from custom_components.kessil_wifi.const import CONF_GID, DOMAIN

from .fake_dongle import DEFAULT_SERIAL


async def _user_flow(hass, host="127.0.0.1", port=8888):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: host, CONF_PORT: port}
    )


async def test_user_flow_creates_an_entry(hass, dongle):
    result = await _user_flow(hass, port=dongle.port)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DEFAULT_SERIAL
    assert result["data"][CONF_HOST] == "127.0.0.1"


async def test_user_flow_stores_the_group_the_lamps_are_in(hass, dongle):
    result = await _user_flow(hass, port=dongle.port)

    assert result["data"][CONF_GID] == dongle.gid


async def test_user_flow_shows_an_error_when_the_dongle_is_unreachable(hass, dongle):
    dongle.fail_connections = True

    result = await _user_flow(hass, port=dongle.port)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_recovers_after_a_failed_attempt(hass, dongle):
    dongle.fail_connections = True
    await _user_flow(hass, port=dongle.port)

    dongle.fail_connections = False
    result = await _user_flow(hass, port=dongle.port)

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_the_same_dongle_cannot_be_added_twice(hass, dongle, setup_integration):
    result = await _user_flow(hass, port=dongle.port)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
