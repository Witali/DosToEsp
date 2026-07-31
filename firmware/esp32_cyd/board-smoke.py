#!/usr/bin/env python3
"""Reset a CYD board and verify the DosToEsp native smoke markers."""

from __future__ import annotations

import argparse
import sys
import time

import serial


SUCCESS = "D2E_NATIVE_OK,exit=42,ax=4c2a,cx=0000,instructions=15"
DONE = "D2E_BOARD_DONE,0"


def capture(port_name: str, baud: int, timeout: float) -> list[str]:
    port = serial.Serial()
    port.port = port_name
    port.baudrate = baud
    port.timeout = 0.2
    port.dsrdtr = False
    port.rtscts = False
    port.dtr = False
    port.rts = False
    port.open()
    try:
        port.reset_input_buffer()
        # GPIO0 remains released while RTS pulses EN low.
        port.dtr = False
        port.rts = True
        time.sleep(0.2)
        port.rts = False
        time.sleep(0.05)
        port.reset_input_buffer()

        data = bytearray()
        text = ""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data.extend(port.read(512))
            text = data.decode("ascii", errors="ignore")
            if SUCCESS in text and DONE in text:
                break
        return [line.strip() for line in text.splitlines() if line.strip()]
    finally:
        port.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM8")
    parser.add_argument("--baud", type=int, action="append")
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()

    bauds = args.baud or [460800, 115200]
    for baud in bauds:
        lines = capture(args.port, baud, args.timeout)
        joined = "\n".join(lines)
        if SUCCESS in joined and DONE in joined:
            for line in lines:
                if line.startswith("D2E_"):
                    print(line)
            print(f"board smoke passed on {args.port} at {baud} baud")
            return 0
        print(f"no valid smoke markers at {baud} baud", file=sys.stderr)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
