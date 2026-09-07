"""Constants for the Kessil WiFi integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "kessil_wifi"

CONF_GID: Final = "gid"

DEFAULT_PORT: Final = 8888
DEFAULT_SCAN_INTERVAL: Final = 30

MANUFACTURER: Final = "Kessil"

# ── Channel mapping ───────────────────────────────────────────────────────
#
# The dongle exposes five channels (UI1..UI5). On an A360X Tuna Sun only the
# first two are driven, matching the fixture's two physical knobs.
#
# NOT YET VISUALLY CONFIRMED: which knob is which. Live testing proved both
# channels are writable and read back correctly, but nobody has watched the
# tank to confirm UI1 is intensity rather than colour. If the mapping turns
# out to be reversed, swapping these two values is the only change needed.
CHANNEL_INTENSITY: Final = 0
CHANNEL_COLOR: Final = 1

# Approximate colour temperature range for the A360X Tuna Sun. These bound the
# HA colour-temp slider and still need calibrating against the real fixture.
MIN_COLOR_TEMP_KELVIN: Final = 2700
MAX_COLOR_TEMP_KELVIN: Final = 6500
