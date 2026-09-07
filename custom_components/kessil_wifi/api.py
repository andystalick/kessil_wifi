"""Async client for the Kessil WiFi dongle.

Plain JSON over TCP 8888. No auth, no encryption, no handshake. A fresh
connection is opened per command; the dongle closes the socket after replying.

Three quirks drive the shape of this module, all confirmed against a live
A360X Tuna Sun (dongle firmware 1.5.13) on 2026-09-07:

1. Group commands nest their fields inside ``data`` and spell the group id
   ``GID`` in uppercase. Lowercase ``gid`` is rejected with "Invalid GID".
2. Writes only take effect with ``save: 1``. With ``save: 0`` the dongle
   returns ``code: 0`` and silently changes nothing.
3. Writes set individual ``UI1``..``UI5`` fields; reads return a ``UI`` array.
   Sending a ``UI`` array on a write is accepted and ignored.

The dongle also refuses rapid reconnects, so commands are serialised behind a
lock and paced by ``min_command_interval``.

This module deliberately has no Home Assistant imports so it can be tested
standalone.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 8888
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 5.0
#: The dongle drops connections that arrive back-to-back.
DEFAULT_MIN_COMMAND_INTERVAL = 0.35

CHANNEL_COUNT = 5
CHANNEL_MAX = 255

DTYPE_GROUP = 3
DTYPE_DEVICE_INFO = 114
DTYPE_PING = 117


class KessilError(Exception):
    """Base error for all dongle failures."""


class KessilConnectionError(KessilError):
    """The dongle could not be reached, or gave no usable reply."""


class KessilProtocolError(KessilError):
    """The dongle replied with an error code."""


@dataclass(frozen=True)
class LampInfo:
    """A single lamp attached to the dongle."""

    kid: int
    gid: int
    model: str
    firmware_version: str
    lamp_type: int


@dataclass(frozen=True)
class DeviceInfo:
    """Dongle-level metadata, from dtype 114."""

    serial: str
    firmware_version: str
    ssid: str
    lamps: list[LampInfo] = field(default_factory=list)
    group_ids: list[int] = field(default_factory=list)

    @property
    def default_gid(self) -> int:
        """The group to control: whichever group the lamps actually live in."""
        if self.lamps:
            return self.lamps[0].gid
        return self.group_ids[0] if self.group_ids else 2


@dataclass(frozen=True)
class GroupState:
    """The current state of one lamp group, from dtype 3."""

    gid: int
    ui: list[int]
    pid: int
    pause: int = 0
    name: str = ""
    lamp_type: int = 0

    @property
    def is_manual_mode(self) -> bool:
        """True when no onboard program owns the group.

        Writing any manual value flips the group into this mode permanently;
        the dongle offers no documented way back to a program.
        """
        return self.pid < 0

    @property
    def is_paused(self) -> bool:
        return bool(self.pause)

    def channel(self, index: int) -> int:
        """Return one channel value, or 0 if the dongle omitted it."""
        return self.ui[index] if index < len(self.ui) else 0


def _clamp(value: int) -> int:
    return max(0, min(CHANNEL_MAX, int(value)))


def _has_complete_json_object(buffer: bytes) -> bool:
    """Whether ``buffer`` already holds one whole JSON object."""
    text = buffer.decode(errors="replace")
    start = text.find("{")
    if start < 0:
        return False
    try:
        json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return False
    return True


class KessilAuthlessClient:
    """Talks to one lamp group on one dongle.

    Named for the protocol's defining feature: there is no authentication of
    any kind, so anything on the LAN can drive these lamps.
    """

    def __init__(
        self,
        host: str,
        *,
        port: int = DEFAULT_PORT,
        gid: int = 2,
        min_command_interval: float = DEFAULT_MIN_COMMAND_INTERVAL,
    ) -> None:
        self._host = host
        self._port = port
        self._gid = gid
        self._min_interval = min_command_interval
        self._lock = asyncio.Lock()
        self._last_command_at: float | None = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def gid(self) -> int:
        return self._gid

    # ── transport ─────────────────────────────────────────────────────────

    async def _async_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send one command and return the parsed reply.

        Serialised behind a lock and paced, because overlapping or
        back-to-back connections make the dongle drop requests outright.
        """
        async with self._lock:
            await self._async_wait_for_slot()
            try:
                return await self._async_roundtrip(payload)
            finally:
                self._last_command_at = asyncio.get_running_loop().time()

    async def _async_wait_for_slot(self) -> None:
        if self._last_command_at is None or self._min_interval <= 0:
            return
        elapsed = asyncio.get_running_loop().time() - self._last_command_at
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)

    async def _async_roundtrip(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        _LOGGER.debug("kessil %s tx: %s", self._host, raw.decode())

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=CONNECT_TIMEOUT,
            )
        except (OSError, TimeoutError) as err:
            raise KessilConnectionError(
                f"Cannot connect to {self._host}:{self._port}: {err}"
            ) from err

        try:
            writer.write(raw)
            await writer.drain()
            body = await asyncio.wait_for(
                self._async_read_reply(reader), timeout=READ_TIMEOUT
            )
        except (OSError, TimeoutError) as err:
            raise KessilConnectionError(
                f"Lost connection to {self._host}: {err}"
            ) from err
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()

        return self._parse(body)

    async def _async_read_reply(self, reader: asyncio.StreamReader) -> bytes:
        """Read until one complete JSON object has arrived.

        The dongle usually closes the socket after replying, but not always --
        and when it lingers, waiting for EOF times out every command. So stop
        as soon as the bytes so far parse as a complete object.
        """
        buffer = b""
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                return buffer
            buffer += chunk
            if _has_complete_json_object(buffer):
                return buffer

    def _parse(self, body: bytes) -> dict[str, Any]:
        """Parse a reply.

        The dongle emits sloppy JSON (stray newlines, inconsistent spacing) and
        can append a second object when it processes the closing EOF as another
        command, so only the first object is decoded.
        """
        if not body:
            raise KessilConnectionError("Dongle closed the connection without replying")

        text = body.decode(errors="replace").strip()
        _LOGGER.debug("kessil %s rx: %s", self._host, text)
        start = text.find("{")
        if start < 0:
            raise KessilConnectionError(f"Unparseable reply: {text[:120]!r}")

        try:
            response, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError as err:
            raise KessilConnectionError(
                f"Malformed JSON reply: {text[:120]!r}"
            ) from err

        if not isinstance(response, dict):
            raise KessilConnectionError(f"Unexpected reply shape: {text[:120]!r}")

        if response.get("code") != 0:
            raise KessilProtocolError(response.get("msg") or "Unknown dongle error")

        return response

    # ── commands ──────────────────────────────────────────────────────────

    async def async_get_device_info(self) -> DeviceInfo:
        """Read dongle metadata (dtype 114)."""
        response = await self._async_command({"dtype": DTYPE_DEVICE_INFO, "data": ""})
        lamps = [
            LampInfo(
                kid=lamp.get("KID", 0),
                gid=lamp.get("GID", 0),
                model=lamp.get("model", ""),
                firmware_version=lamp.get("FWVer", ""),
                lamp_type=lamp.get("type", 0),
            )
            for lamp in response.get("lamps", [])
        ]
        return DeviceInfo(
            serial=response.get("sn", ""),
            firmware_version=response.get("ver", ""),
            ssid=response.get("SSID", ""),
            lamps=lamps,
            group_ids=response.get("group_ids", []),
        )

    async def async_ping(self) -> bool:
        """Cheap reachability check (dtype 117)."""
        try:
            await self._async_command({"dtype": DTYPE_PING, "data": ""})
        except KessilError:
            return False
        return True

    async def async_get_state(self) -> GroupState:
        """Read the group's current channels and mode (dtype 3)."""
        response = await self._async_command(
            {"dtype": DTYPE_GROUP, "data": {"GID": self._gid}}
        )
        return self._group_from(response)

    async def async_set_channels(
        self,
        *,
        intensity: int | None = None,
        color: int | None = None,
        extra: dict[int, int] | None = None,
    ) -> GroupState:
        """Write channel values and return the resulting state.

        Only the channels given are written; the rest are carried over from the
        current state so a brightness change cannot clobber colour.
        """
        current = await self.async_get_state()
        channels = list(current.ui[:CHANNEL_COUNT])
        channels += [0] * (CHANNEL_COUNT - len(channels))

        if intensity is not None:
            channels[0] = _clamp(intensity)
        if color is not None:
            channels[1] = _clamp(color)
        for index, value in (extra or {}).items():
            channels[index] = _clamp(value)

        data: dict[str, Any] = {"GID": self._gid}
        for index, value in enumerate(channels):
            data[f"UI{index + 1}"] = value
        # Mandatory: with save:0 the dongle acknowledges and does nothing.
        data["save"] = 1

        response = await self._async_command({"dtype": DTYPE_GROUP, "data": data})
        return self._group_from(response)

    def _group_from(self, response: dict[str, Any]) -> GroupState:
        group = response.get("group")
        if not isinstance(group, dict):
            raise KessilConnectionError("Reply contained no group object")

        ui = group.get("UI") or []
        return GroupState(
            gid=group.get("gid", self._gid),
            ui=[int(v) for v in ui],
            pid=group.get("pid", -1),
            pause=group.get("pause", 0),
            name=group.get("name", ""),
            lamp_type=group.get("type", 0),
        )
