#!/usr/bin/env python3
"""Welder configuration, connection and control example; offline by default.

Demonstration inputs are restricted to the isolated mock namespace.
"""

import argparse
import json
from pathlib import Path
from aotai_sdk import AotaiClient, ApiError


def require_ok(response, label):
    if response.status != 200:
        raise RuntimeError(
            f"{label}: status={response.status} message={response.message!r}"
        )
    print(
        f"{label}: status={response.status} result={getattr(response, 'result', None)!r} message={getattr(response, 'message', '')!r}"
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true")
    p.add_argument("--endpoint-prefix", default="")
    p.add_argument(
        "--input", default=str(Path(__file__).parents[1] / "data/device-control.json")
    )
    args = p.parse_args()
    spec = json.loads(Path(args.input).read_text())
    if not args.execute:
        print(
            "offline: add --execute --endpoint-prefix /api_device_mock only for the isolated mock"
        )
        return 0
    if (
        spec.get("demonstration_only") is True
        and args.endpoint_prefix != "/api_device_mock"
    ):
        raise SystemExit(
            "refusing demonstration input outside /api_device_mock"
        )
    if spec.get("demonstration_only") is not True and not spec.get("site_confirmed"):
        raise SystemExit("refusing field input without site_confirmed:true")
    if not isinstance(spec.get("demonstration_only"), bool):
        raise ValueError("demonstration_only must be an explicit boolean")
    if spec["demonstration_only"] is False and spec.get("site_confirmed") is not True:
        raise ValueError("site_confirmed must be boolean true for field input")
    w = spec["welder"]
    try:
        with AotaiClient(endpoint_prefix=args.endpoint_prefix) as client:
            require_ok(client.welder_config("", w["config_data"]), "config")
            require_ok(client.welder_connect(w["weld_ip"], True), "connect")
            cert = client.welder_certify(w["certificate"])
            require_ok(cert, "certify")
            if cert.result != 1:
                raise RuntimeError("certify result is not 1")
            require_ok(client.welder_robot_ready(True), "robot_ready")
            require_ok(client.welder_current(w["current"]), "current")
            require_ok(client.welder_synergic_mode(w["synergic_mode"]), "synergic_mode")
            require_ok(client.welder_voltage(w["voltage"]), "voltage")
            enabled = client.welder_enable(w["enable"])
            require_ok(enabled, "enable")
            if enabled.result != w["enable"]:
                raise RuntimeError("enable cache bit does not match requested enable")
            require_ok(client.welder_welding(True), "welding_accept")
            arc = client.welder_status("is_arcing")
            require_ok(arc, "is_arcing")
            if arc.result != 1:
                raise RuntimeError(
                    "is_arcing is not 1; start request was only accepted"
                )
            require_ok(client.welder_welding(False), "welding_stop_accept")
            operating = client.welder_status("weld_operate")
            require_ok(operating, "weld_operate")
            if operating.result != 0:
                raise RuntimeError("weld_operate is not 0 after stop request")
            disabled = client.welder_enable(0)
            require_ok(disabled, "disable")
            if disabled.result != 0:
                raise RuntimeError("disable cache bit is not 0")
            require_ok(client.welder_robot_ready(False), "robot_not_ready")
    except ApiError as exc:
        print(f"SDK error: {exc}; raw={exc.raw!r}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
