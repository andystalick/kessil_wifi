"""Conversions between dongle channel values and Home Assistant units.

Kept free of Home Assistant imports so the arithmetic can be tested directly.

The dongle's colour channel is a linear 0-255 mix between the fixture's warm
and cool ends. Home Assistant expresses colour as a temperature in kelvin, so
the two are mapped linearly onto each other. The kelvin bounds are nominal for
an A360X Tuna Sun and still want calibrating against the real fixture.
"""

from __future__ import annotations

CHANNEL_MAX = 255


def channel_to_kelvin(channel: int, min_kelvin: int, max_kelvin: int) -> int:
    """Convert a 0-255 colour channel to a colour temperature."""
    ratio = max(0, min(CHANNEL_MAX, channel)) / CHANNEL_MAX
    return round(min_kelvin + ratio * (max_kelvin - min_kelvin))


def kelvin_to_channel(kelvin: int, min_kelvin: int, max_kelvin: int) -> int:
    """Convert a colour temperature to a 0-255 colour channel."""
    span = max_kelvin - min_kelvin
    if span <= 0:
        return 0
    ratio = (kelvin - min_kelvin) / span
    return max(0, min(CHANNEL_MAX, round(ratio * CHANNEL_MAX)))
