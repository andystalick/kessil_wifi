"""Tests for the Kessil light entity."""

from __future__ import annotations

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)

from .fake_dongle import DEFAULT_SERIAL

ENTITY_ID = f"light.kessil_{DEFAULT_SERIAL.lower()}"


async def _call(hass, service, **data):
    await hass.services.async_call(
        LIGHT_DOMAIN,
        service,
        {ATTR_ENTITY_ID: ENTITY_ID, **data},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_light_entity_is_created(hass, setup_integration):
    assert hass.states.get(ENTITY_ID) is not None


async def test_light_reports_state_from_the_dongle(hass, dongle, setup_integration):
    state = hass.states.get(ENTITY_ID)

    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == dongle.ui[0]


async def test_light_is_off_when_intensity_is_zero(hass, dongle, config_entry):
    """A lamp with colour set but no intensity is off, not on."""
    dongle.ui = [0, 120, 0, 0, 0]
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(ENTITY_ID).state == STATE_OFF


async def test_turn_on_with_brightness_writes_the_intensity_channel(
    hass, dongle, setup_integration
):
    await _call(hass, SERVICE_TURN_ON, **{ATTR_BRIGHTNESS: 200})

    assert dongle.ui[0] == 200
    assert hass.states.get(ENTITY_ID).attributes[ATTR_BRIGHTNESS] == 200


async def test_turn_on_preserves_the_colour_channel(hass, dongle, setup_integration):
    dongle.ui = [150, 90, 0, 0, 0]

    await _call(hass, SERVICE_TURN_ON, **{ATTR_BRIGHTNESS: 200})

    assert dongle.ui[1] == 90


async def test_turn_on_with_colour_temp_writes_the_colour_channel(
    hass, dongle, setup_integration
):
    await _call(hass, SERVICE_TURN_ON, **{ATTR_COLOR_TEMP_KELVIN: 6500})

    assert dongle.ui[1] == 255


async def test_turn_off_zeroes_only_the_intensity_channel(
    hass, dongle, setup_integration
):
    dongle.ui = [150, 90, 0, 0, 0]

    await _call(hass, SERVICE_TURN_OFF)

    assert dongle.ui[0] == 0
    assert dongle.ui[1] == 90
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


async def test_turn_on_after_turn_off_restores_the_previous_brightness(
    hass, dongle, setup_integration
):
    dongle.ui = [180, 90, 0, 0, 0]
    await _call(hass, SERVICE_TURN_ON, **{ATTR_BRIGHTNESS: 180})

    await _call(hass, SERVICE_TURN_OFF)
    assert dongle.ui[0] == 0

    await _call(hass, SERVICE_TURN_ON)

    assert dongle.ui[0] == 180


async def test_writes_always_use_save_1(hass, dongle, setup_integration):
    """A write with save:0 is silently ignored by the real dongle."""
    await _call(hass, SERVICE_TURN_ON, **{ATTR_BRIGHTNESS: 100})

    writes = [
        r for r in dongle.requests if r["dtype"] == 3 and "UI1" in r.get("data", {})
    ]
    assert writes
    assert all(w["data"]["save"] == 1 for w in writes)


async def test_manual_mode_is_exposed_as_an_attribute(hass, dongle, setup_integration):
    """Writing from HA ends the lamp's onboard program; surface that."""
    assert hass.states.get(ENTITY_ID).attributes["manual_mode"] is False

    await _call(hass, SERVICE_TURN_ON, **{ATTR_BRIGHTNESS: 100})

    assert hass.states.get(ENTITY_ID).attributes["manual_mode"] is True
