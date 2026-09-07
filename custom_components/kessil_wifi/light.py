"""Light platform for the Kessil WiFi integration."""

from __future__ import annotations

from typing import Any, ClassVar

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo as HaDeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import KessilError
from .const import (
    CHANNEL_COLOR,
    CHANNEL_INTENSITY,
    DOMAIN,
    MANUFACTURER,
    MAX_COLOR_TEMP_KELVIN,
    MIN_COLOR_TEMP_KELVIN,
)
from .coordinator import KessilConfigEntry, KessilCoordinator
from .scaling import channel_to_kelvin, kelvin_to_channel

# The coordinator serialises device access, so the platform must not add its
# own parallelism on top.
PARALLEL_UPDATES = 0

#: Used when turning on a lamp that has no remembered brightness.
DEFAULT_ON_BRIGHTNESS = 255


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KessilConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Kessil light."""
    async_add_entities([KessilLight(entry.runtime_data)])


class KessilLight(CoordinatorEntity[KessilCoordinator], LightEntity):
    """A Kessil lamp group, exposed as a single dimmable, colour-temp light."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes: ClassVar[set[ColorMode]] = {ColorMode.COLOR_TEMP}
    _attr_min_color_temp_kelvin = MIN_COLOR_TEMP_KELVIN
    _attr_max_color_temp_kelvin = MAX_COLOR_TEMP_KELVIN

    def __init__(self, coordinator: KessilCoordinator) -> None:
        super().__init__(coordinator)
        device = coordinator.device_info
        serial = device.serial if device else coordinator.config_entry.entry_id
        gid = coordinator.client.gid

        self._attr_unique_id = f"{serial}_group_{gid}"
        self._attr_device_info = HaDeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer=MANUFACTURER,
            name=f"Kessil {serial}",
            model=device.lamps[0].model if device and device.lamps else None,
            sw_version=device.firmware_version if device else None,
            configuration_url=f"http://{coordinator.client.host}",
        )
        # Remembering the last lit level lets turn_on restore it, since the
        # dongle stores "off" as intensity 0 and forgets the previous value.
        self._last_brightness: int | None = None

    @property
    def is_on(self) -> bool:
        """Whether the lamp is emitting light."""
        return self.coordinator.data.channel(CHANNEL_INTENSITY) > 0

    @property
    def brightness(self) -> int:
        """Current brightness, on Home Assistant's 0-255 scale.

        The dongle uses 0-255 for its channels too, so this is a direct read.
        """
        return self.coordinator.data.channel(CHANNEL_INTENSITY)

    @property
    def color_temp_kelvin(self) -> int:
        """Current colour temperature."""
        return channel_to_kelvin(
            self.coordinator.data.channel(CHANNEL_COLOR),
            MIN_COLOR_TEMP_KELVIN,
            MAX_COLOR_TEMP_KELVIN,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the onboard program state.

        Once Home Assistant writes any value the group drops to manual mode and
        its onboard Kessil schedule stops running, so surface that plainly.
        """
        state = self.coordinator.data
        return {
            "manual_mode": state.is_manual_mode,
            "onboard_program_id": None if state.is_manual_mode else state.pid,
            "group_name": state.name,
            "paused": state.is_paused,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the lamp on, optionally setting brightness and colour."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is None:
            current = self.coordinator.data.channel(CHANNEL_INTENSITY)
            brightness = current or self._last_brightness or DEFAULT_ON_BRIGHTNESS

        color: int | None = None
        if (kelvin := kwargs.get(ATTR_COLOR_TEMP_KELVIN)) is not None:
            color = kelvin_to_channel(
                kelvin, MIN_COLOR_TEMP_KELVIN, MAX_COLOR_TEMP_KELVIN
            )

        await self._async_write(intensity=brightness, color=color)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the lamp off.

        Only the intensity channel is zeroed; the colour channel is left alone
        so the previous colour returns on the next turn-on.
        """
        if (current := self.coordinator.data.channel(CHANNEL_INTENSITY)) > 0:
            self._last_brightness = current
        await self._async_write(intensity=0, color=None)

    async def _async_write(self, *, intensity: int, color: int | None) -> None:
        """Push channel values to the dongle and publish the result."""
        try:
            state = await self.coordinator.client.async_set_channels(
                intensity=intensity, color=color
            )
        except KessilError as err:
            raise HomeAssistantError(f"Failed to update Kessil light: {err}") from err

        if intensity > 0:
            self._last_brightness = intensity
        self.coordinator.async_set_updated_data(state)
