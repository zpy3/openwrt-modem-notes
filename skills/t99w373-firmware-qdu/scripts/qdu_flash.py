#!/usr/bin/env python3
"""MBIM QDU flash for T99W373 (via mbim-proxy).

Prereq (as root):
  systemctl stop ModemManager
  killall mbim-proxy 2>/dev/null || true
  /usr/libexec/mbim-proxy &
  echo on > /sys/bus/pci/devices/<BDF>/power/control   # keep looping

Usage:
  python3 qdu_flash.py /path/to/ota.bin [/dev/wwan0mbim0]
"""

from __future__ import annotations

import sys
import time

import gi

gi.require_version("Mbim", "1.0")
from gi.repository import Mbim, Gio, GLib  # noqa: E402


def parse_max_xfer(parsed) -> int:
    if hasattr(parsed, "out_max_transfer_size"):
        return int(parsed.out_max_transfer_size)
    if isinstance(parsed, tuple):
        # GI often returns (True, out_max_transfer_size=N, ...)
        # [0] is success bool — NEVER use int(parsed[0]) as size
        for item in parsed:
            if isinstance(item, int) and item > 1:
                return item
        if len(parsed) > 1 and isinstance(parsed[1], int) and parsed[1] > 1:
            return int(parsed[1])
    raise RuntimeError(f"cannot parse max transfer size from {parsed!r}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    ota_path = sys.argv[1]
    dev_path = sys.argv[2] if len(sys.argv) > 2 else "/dev/wwan0mbim0"
    blob = open(ota_path, "rb").read()
    print(f"ota {ota_path} size={len(blob)}", flush=True)
    print(f"dev {dev_path}", flush=True)

    loop = GLib.MainLoop()
    state: dict = {"err": None, "dev": None, "off": 0, "n": 0, "t0": 0, "max_xfer": 65536}

    def finish(err=None, msg=None):
        if err is not None:
            state["err"] = err
            print("FAIL:", err, flush=True)
        if msg:
            print(msg, flush=True)
        try:
            if state.get("dev"):
                state["dev"].close_force()
        except Exception:
            pass
        loop.quit()

    def send(msg, timeout, cb):
        def on_cmd(d, res):
            try:
                resp = d.command_finish(res)
            except Exception as e:
                finish(e)
                return
            cb(resp)

        state["dev"].command(msg, timeout, None, on_cmd)

    def on_new(obj, res):
        try:
            dev = Mbim.Device.new_finish(res)
            state["dev"] = dev
            print("open PROXY", flush=True)
            dev.open_full(Mbim.DeviceOpenFlags.PROXY, 90, None, on_open)
        except Exception as e:
            finish(e)

    def on_open(dev, res):
        try:
            dev.open_finish(res)
            print("OPEN OK", flush=True)
        except Exception as e:
            finish(e)
            return
        print("caps", flush=True)
        send(Mbim.Message.device_caps_query_new(), 30, on_caps)

    def on_caps(_resp):
        print("caps ok; session START LE", flush=True)
        send(
            Mbim.Message.qdu_update_session_set_new(
                Mbim.QduSessionAction.START, Mbim.QduSessionType.LE
            ),
            120,
            on_session,
        )

    def on_session(resp):
        print("session", Mbim.Message.qdu_update_session_response_parse(resp), flush=True)
        print("file open PACKAGE", flush=True)
        send(
            Mbim.Message.qdu_file_open_set_new(Mbim.QduFileType.PACKAGE, len(blob)),
            120,
            on_file_open,
        )

    def on_file_open(resp):
        parsed = Mbim.Message.qdu_file_open_response_parse(resp)
        print("file_open", parsed, flush=True)
        device_max = parse_max_xfer(parsed)
        state["max_xfer"] = min(device_max, 65536)
        if state["max_xfer"] < 1024:
            finish(f"refusing tiny chunk size {state['max_xfer']}")
            return
        state["off"] = 0
        state["n"] = 0
        state["t0"] = time.time()
        print(f"chunk {state['max_xfer']} (device_max {device_max})", flush=True)
        write_next()

    def write_next():
        off = state["off"]
        total = len(blob)
        if off >= total:
            print("WRITE DONE", flush=True)
            print("session STOP (may fail if modem resets)", flush=True)
            send(
                Mbim.Message.qdu_update_session_set_new(
                    Mbim.QduSessionAction.STOP, Mbim.QduSessionType.LE
                ),
                300,
                on_stop,
            )
            return

        chunk = blob[off : off + state["max_xfer"]]

        def on_write(_resp):
            state["off"] += len(chunk)
            state["n"] += 1
            if state["n"] % 50 == 0 or state["off"] >= total:
                pct = 100.0 * state["off"] / total
                rate = state["off"] / max(time.time() - state["t0"], 1) / (1024 * 1024)
                print(
                    f"write {state['off']}/{total} ({pct:.1f}%) {rate:.2f} MiB/s",
                    flush=True,
                )
            write_next()

        def on_cmd(d, res):
            try:
                resp = d.command_finish(res)
            except Exception as e:
                finish(e)
                return
            on_write(resp)

        try:
            req = Mbim.Message.qdu_file_write_set_new(chunk)
        except TypeError:
            req = Mbim.Message.qdu_file_write_set_new(GLib.Bytes.new(chunk))
        state["dev"].command(req, 180, None, on_cmd)

    def on_stop(resp):
        try:
            print("stop", Mbim.Message.qdu_update_session_response_parse(resp), flush=True)
        except Exception as e:
            print("stop parse skipped:", e, flush=True)
        finish(msg="SUCCESS — verify firmware revision (e.g. 063) via mmcli/AT")

    Mbim.Device.new(Gio.File.new_for_path(dev_path), None, on_new)
    GLib.timeout_add_seconds(60 * 60, lambda: (finish("global timeout"), False)[1])
    loop.run()
    return 2 if state["err"] else 0


if __name__ == "__main__":
    sys.exit(main())
