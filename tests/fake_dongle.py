"""A fake Kessil dongle that reproduces the real device's quirks.

Behaviours modelled from live testing against a real dongle (fw 1.5.13):

* Fresh TCP connection per command; server closes the socket after replying.
* Request key is ``dtype`` (lowercase); response key is ``dType`` (capital T).
* dtype 3 requires the group id as uppercase ``GID`` *inside* a nested ``data``
  object. Lowercase ``gid`` returns ``{"code": -1, "msg": "Invalid GID"}``.
* Writes require ``save: 1``. With ``save: 0`` the device replies ``code: 0``
  and changes nothing -- the trap that stalled this project for months.
* Writes take individual ``UI1``..``UI5`` fields. A ``UI`` array in a write is
  accepted and silently ignored.
* A successful write flips ``pid`` to -1 (manual mode), ending the onboard program.
* Responses contain sloppy whitespace and stray newlines, so clients must not
  assume tidy JSON.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any

DEFAULT_SERIAL = "KTEST0000001"
DEFAULT_FIRMWARE = "1.5.13"


class FakeDongle:
    """An asyncio TCP server that speaks the Kessil dongle protocol."""

    def __init__(
        self,
        *,
        serial: str = DEFAULT_SERIAL,
        gid: int = 2,
        ui: list[int] | None = None,
        pid: int = 1,
    ) -> None:
        self.serial = serial
        self.gid = gid
        self.ui = list(ui) if ui is not None else [150, 150, 0, 0, 0]
        self.pid = pid
        self.pause = 0
        self.requests: list[dict[str, Any]] = []
        # Test knobs
        self.fail_connections = False
        self.drop_without_reply = False
        #: Reply but hold the socket open. The real dongle does this, so the
        #: client must not wait for EOF to decide a reply is complete.
        self.keep_connection_open = False
        self.connection_count = 0

        self._server: asyncio.Server | None = None
        self.port: int = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.connection_count += 1
        try:
            if self.fail_connections:
                writer.close()
                return

            raw = await reader.read(8192)
            if not raw:
                writer.close()
                return

            try:
                req = json.loads(raw.decode())
            except json.JSONDecodeError:
                writer.write(self._err(-1, "Invalid command or parameters"))
                await writer.drain()
                writer.close()
                return

            self.requests.append(req)

            if self.drop_without_reply:
                writer.close()
                return

            writer.write(self._dispatch(req))
            await writer.drain()

            if self.keep_connection_open:
                # Outlive any sane client read timeout.
                await asyncio.sleep(30)
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            with suppress(Exception):
                writer.close()

    # ── protocol ──────────────────────────────────────────────────────────

    def _err(self, dtype: int, msg: str) -> bytes:
        return f'{{"msg":"{msg}","code":-1, "dType":{dtype}}}\n'.encode()

    def _dispatch(self, req: dict[str, Any]) -> bytes:
        dtype = req.get("dtype")
        if dtype == 114:
            return self._device_info()
        if dtype == 117:
            return (
                f'{{"msg":"Success","code":0, "dType":117,"SN":"{self.serial}",'
                f'"siblings":"{self.serial}","APEX":0}}'.encode()
            )
        if dtype == 3:
            return self._group_cmd(req)
        # Anything else falls through the jump table.
        return self._err(-1, "Invalid command or parameters")

    def _device_info(self) -> bytes:
        lamps = ",\n".join(
            f'{{"KID":{kid},\n"GID":{self.gid},"lGID":-1,"rGID":-1,'
            f'"model":"A360X Tuna Sun",\n"FWVer":"1.5","type":2, "temp":0}}'
            for kid in (23003622, 23003625)
        )
        return (
            f'{{"code":0,"msg":"Success", "dType":114,"sn":"{self.serial}", '
            f'"ver":"{DEFAULT_FIRMWARE}", "SSID":"Example Network","ENC":"psk2", '
            f'"timezone":"America/Chicago" , "demo":0, "BAND": 1,'
            f'"lamps":[{lamps}\n], "group_ids":[1,{self.gid},26,27]}}'
        ).encode()

    def _group_cmd(self, req: dict[str, Any]) -> bytes:
        data = req.get("data")
        # The real device wants a nested object with uppercase GID.
        if not isinstance(data, dict) or "GID" not in data:
            return self._err(3, "Invalid GID")
        if data["GID"] != self.gid:
            return self._err(3, "Invalid GID")

        # A write only happens with save == 1. Otherwise: silent no-op.
        if int(data.get("save", 0)) == 1:
            wrote = False
            for idx in range(5):
                key = f"UI{idx + 1}"
                if key in data:
                    self.ui[idx] = int(data[key])
                    wrote = True
            if wrote:
                # Committing manual values ends the onboard program.
                self.pid = -1
            elif "UI" in data:
                # UI array on a write is accepted but ignored; the device still
                # commits, zeroing the channels and dropping to manual mode.
                self.ui = [0, 0, 0, 0, 0]
                self.pid = -1
            if "pause" in data:
                self.pause = int(data["pause"])

        return self._group_response()

    def _group_response(self) -> bytes:
        ui = ", ".join(str(v) for v in self.ui)
        return (
            f'{{\n  "code":0,\n  "msg":"",\n  "group":{{"gid":{self.gid}, '
            f'"pid":{self.pid}, "eid":-1, "type":2, "hasLamps":2, '
            f'"name":"Default TS","pause":{self.pause}, "startDate":1778286307,'
            f'"UI":[{ui}],"accl":{{"start":96, "period":7, "enabled":0}},'
            f'"lunar":{{"start":1200, "end":480, "high":120,"color":0, '
            f'"phase":0, "enabled":0}}}}, "dType":3}}'
        ).encode()
