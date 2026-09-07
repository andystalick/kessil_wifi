#!/usr/bin/env python3
"""Exercise the integration's real client against a real dongle.

The test suite runs against a fake dongle, which only proves the client matches
our understanding of the protocol. This proves that understanding is right.

    python3 verify_live.py <dongle-ip>

Restores the starting channel values when it finishes.
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "custom_components")

from kessil_wifi.api import KessilAuthlessClient, KessilError  # noqa: E402


async def main(host: str) -> int:
    client = KessilAuthlessClient(host, gid=2)

    print(f"→ dtype 114  device info  ({host})")
    try:
        info = await client.async_get_device_info()
    except KessilError as err:
        print(f"  FAIL: {err}")
        return 1
    print(f"  serial={info.serial} fw={info.firmware_version} groups={info.group_ids}")
    print(f"  lamps={[(lamp.model, lamp.gid) for lamp in info.lamps]}")
    print(f"  default gid={info.default_gid}")

    print("\n→ dtype 117  ping")
    print(f"  reachable={await client.async_ping()}")

    print("\n→ dtype 3    read state")
    state = await client.async_get_state()
    original = list(state.ui)
    print(f"  UI={state.ui} pid={state.pid} manual={state.is_manual_mode} "
          f"name={state.name!r}")

    print("\n→ dtype 3    write intensity=90 color=200")
    written = await client.async_set_channels(intensity=90, color=200)
    print(f"  UI={written.ui} manual={written.is_manual_mode}")
    ok = written.ui[0] == 90 and written.ui[1] == 200
    print(f"  {'PASS' if ok else 'FAIL'}: values applied")

    print("\n→ dtype 3    partial write (intensity only) preserves colour")
    partial = await client.async_set_channels(intensity=140)
    keeps_color = partial.ui[1] == 200
    print(f"  UI={partial.ui}")
    print(f"  {'PASS' if keeps_color else 'FAIL'}: colour channel untouched")

    print(f"\n→ restoring original UI={original}")
    final = await client.async_set_channels(
        intensity=original[0], color=original[1]
    )
    print(f"  UI={final.ui}")

    return 0 if (ok and keeps_color) else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
