#!/usr/bin/env python3
"""VZ connect/config -> start capture -> stop capture. Download is a separate example."""

import argparse
import json
import math
import time
from pathlib import Path
from aotai_sdk import Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--config",
        type=Path,
        help="actual VZ connect JSON; guid from discovered camera",
    )
    parser.add_argument("--seconds", type=float, default=1.0)
    parser.add_argument("--prefix", default="")
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error("--seconds must be finite and positive")
    if not args.execute:
        print(
            "Offline: --execute --config CONFIG.json starts/stops acquisition; no point cloud is downloaded automatically."
        )
        return 0
    if args.config is None:
        parser.error("--config is required for explicit acquisition")
    config = json.loads(args.config.read_text())
    if (
        not isinstance(config, dict)
        or config.get("command_type") != "connect"
        or not isinstance(config.get("guid"), str)
        or not config["guid"]
    ):
        parser.error("config needs command_type=connect and actual guid from discovery")
    with Client(endpoint_prefix=args.prefix) as client:
        reply = client.camera_config(json.dumps(config, ensure_ascii=False))
        print(reply.message)  # SDK checks the inner JSON status; keep driver details.
        reply = client.camera_config('{"command_type":"connect_status"}')
        status = json.loads(reply.message)
        if status.get("connect_status") != 1:
            raise ValueError(f"camera not connected; raw={reply.message!r}")
        print(client.camera_control('{"command_type":"start_capture"}').message)
        time.sleep(
            args.seconds
        )  # A capture interval, not evidence that points are ready.
        print(client.camera_control('{"command_type":"stop_capture"}').message)
        print(
            "Capture stop acknowledged. APP PCD file download uses HTTP; see docs/point-cloud-download.md. No frame/unit is inferred."
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(
            f'ERROR: {error}; raw={getattr(error, "raw", None)!r}; acquisition outcome may be unknown'
        )
        raise SystemExit(2)
