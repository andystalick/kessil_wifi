"""Tests for the channel <-> Home Assistant unit conversions."""

from __future__ import annotations

import pytest

from custom_components.kessil_wifi.scaling import (
    channel_to_kelvin,
    kelvin_to_channel,
)

MIN_K = 2700
MAX_K = 6500


def test_zero_channel_is_the_warmest_temperature():
    assert channel_to_kelvin(0, MIN_K, MAX_K) == MIN_K


def test_full_channel_is_the_coolest_temperature():
    assert channel_to_kelvin(255, MIN_K, MAX_K) == MAX_K


def test_midpoint_channel_is_the_middle_of_the_range():
    assert channel_to_kelvin(128, MIN_K, MAX_K) == pytest.approx(4600, abs=20)


def test_kelvin_round_trips_back_to_the_same_channel():
    for channel in (0, 40, 128, 200, 255):
        kelvin = channel_to_kelvin(channel, MIN_K, MAX_K)
        assert kelvin_to_channel(kelvin, MIN_K, MAX_K) == pytest.approx(channel, abs=1)


def test_kelvin_below_range_clamps_to_zero():
    assert kelvin_to_channel(1000, MIN_K, MAX_K) == 0


def test_kelvin_above_range_clamps_to_full():
    assert kelvin_to_channel(9000, MIN_K, MAX_K) == 255


def test_degenerate_range_does_not_divide_by_zero():
    assert kelvin_to_channel(5000, 4000, 4000) == 0
