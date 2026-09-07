"""Tests for the Kessil protocol client."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.kessil_wifi.api import (
    KessilAuthlessClient,
    KessilConnectionError,
    KessilProtocolError,
)

from .fake_dongle import DEFAULT_SERIAL


@pytest.fixture
def client(dongle):
    return KessilAuthlessClient(
        host="127.0.0.1", port=dongle.port, gid=dongle.gid, min_command_interval=0.0
    )


async def test_get_state_returns_current_ui_channels(dongle, client):
    dongle.ui = [150, 90, 0, 0, 0]

    state = await client.async_get_state()

    assert state.ui == [150, 90, 0, 0, 0]
    assert state.gid == 2


async def test_get_state_sends_uppercase_gid_nested_in_data(dongle, client):
    """Lowercase gid is rejected by the device, so the client must send GID."""
    await client.async_get_state()

    assert dongle.requests[-1] == {"dtype": 3, "data": {"GID": 2}}


async def test_set_channels_writes_values(dongle, client):
    await client.async_set_channels(intensity=200, color=60)

    assert dongle.ui == [200, 60, 0, 0, 0]


async def test_set_channels_always_sends_save_1(dongle, client):
    """save:0 is a silent no-op on the real device, so writes must use save:1."""
    await client.async_set_channels(intensity=200, color=60)

    assert dongle.requests[-1]["data"]["save"] == 1


async def test_set_channels_uses_individual_ui_fields_not_an_array(dongle, client):
    """The device ignores a UI array on writes and would zero the channels."""
    await client.async_set_channels(intensity=200, color=60)

    data = dongle.requests[-1]["data"]
    assert data["UI1"] == 200
    assert data["UI2"] == 60
    assert "UI" not in data


async def test_set_channels_clamps_out_of_range_values(dongle, client):
    await client.async_set_channels(intensity=999, color=-5)

    assert dongle.ui[0] == 255
    assert dongle.ui[1] == 0


async def test_set_channels_returns_the_updated_state(dongle, client):
    state = await client.async_set_channels(intensity=10, color=20)

    assert state.ui[:2] == [10, 20]


async def test_state_reports_manual_mode_after_a_write(dongle, client):
    assert dongle.pid == 1

    state = await client.async_set_channels(intensity=10, color=20)

    assert state.pid == -1
    assert state.is_manual_mode is True


async def test_get_device_info_returns_serial_and_firmware(dongle, client):
    info = await client.async_get_device_info()

    assert info.serial == DEFAULT_SERIAL
    assert info.firmware_version == "1.5.13"
    assert info.group_ids == [1, 2, 26, 27]
    assert [lamp.model for lamp in info.lamps] == ["A360X Tuna Sun"] * 2


async def test_wrong_gid_raises_protocol_error(dongle):
    client = KessilAuthlessClient(
        host="127.0.0.1", port=dongle.port, gid=99, min_command_interval=0.0
    )

    with pytest.raises(KessilProtocolError, match="Invalid GID"):
        await client.async_get_state()


async def test_unreachable_host_raises_connection_error(dongle, client):
    dongle.fail_connections = True

    with pytest.raises(KessilConnectionError):
        await client.async_get_state()


async def test_reply_is_used_even_if_the_dongle_holds_the_socket_open(dongle, client):
    """The real dongle does not always close promptly after replying.

    Waiting for EOF to decide the reply is complete makes every command time
    out against the real device.
    """
    dongle.keep_connection_open = True

    state = await client.async_get_state()

    assert state.ui == dongle.ui


async def test_no_reply_raises_connection_error(dongle, client):
    dongle.drop_without_reply = True

    with pytest.raises(KessilConnectionError):
        await client.async_get_state()


async def test_commands_are_serialised_one_connection_at_a_time(dongle, client):
    """The dongle refuses overlapping connections, so commands must not race."""
    seen: list[int] = []
    original = dongle._handle

    async def tracking_handle(reader, writer):
        seen.append(dongle.connection_count)
        await asyncio.sleep(0.02)
        await original(reader, writer)

    dongle._handle = tracking_handle
    await dongle.stop()
    await dongle.start()
    client._port = dongle.port

    await asyncio.gather(*(client.async_get_state() for _ in range(4)))

    # Serialised access means each handler starts after the previous finished.
    assert seen == sorted(seen)


async def test_min_command_interval_paces_requests(dongle):
    """Back-to-back connections make the real device drop requests."""
    client = KessilAuthlessClient(
        host="127.0.0.1", port=dongle.port, gid=dongle.gid, min_command_interval=0.05
    )

    loop = asyncio.get_running_loop()
    start = loop.time()
    await client.async_get_state()
    await client.async_get_state()
    elapsed = loop.time() - start

    assert elapsed >= 0.05


async def test_ping_returns_true_when_reachable(dongle, client):
    assert await client.async_ping() is True


async def test_ping_returns_false_when_unreachable(dongle, client):
    dongle.fail_connections = True

    assert await client.async_ping() is False
