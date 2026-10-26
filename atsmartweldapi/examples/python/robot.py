#!/usr/bin/env python3
"""Robot configuration and control example; offline by default.

The i7 subtype is an example; use the configured model for your robot.
"""

import argparse
import json
from pathlib import Path
from aotai_sdk import AotaiClient, ApiError


def ok(r, name):
    if r.status != 200:
        raise RuntimeError(f"{name}: {r.status} {r.message!r}")
    print(
        f"{name}: status={r.status} result={getattr(r, 'result', None)!r} message={getattr(r, 'message', '')!r}"
    )


def parse_state(reply):
    try:
        state = json.loads(reply.data)
        if not isinstance(state, dict):
            raise ValueError("expected object")
        return state
    except (ValueError, TypeError) as error:
        raise RuntimeError(f"malformed robot status; raw={reply.data!r}") from error


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true")
    p.add_argument("--endpoint-prefix", default="")
    p.add_argument(
        "--input", default=str(Path(__file__).parents[1] / "data/device-control.json")
    )
    a = p.parse_args()
    d = json.loads(Path(a.input).read_text())
    if not a.execute:
        print("offline: no robot request is sent")
        return 0
    if d.get("demonstration_only") is True and a.endpoint_prefix != "/api_device_mock":
        raise SystemExit(
            "refusing demonstration input outside /api_device_mock"
        )
    if d.get("demonstration_only") is not True and not d.get("site_confirmed"):
        raise SystemExit("refusing field input without site_confirmed:true")
    if not isinstance(d.get("demonstration_only"), bool):
        raise ValueError("demonstration_only must be an explicit boolean")
    if d["demonstration_only"] is False and d.get("site_confirmed") is not True:
        raise ValueError("site_confirmed must be boolean true for field input")
    r = d["robot"]
    step = r["step"]
    try:
        with AotaiClient(endpoint_prefix=a.endpoint_prefix) as c:
            ok(
                c.robot_init(
                    r["robot_type"],
                    r["robot_subtype"],
                    r["robot_ip"],
                    r["local_ip"],
                    r["robot_scope"],
                ),
                "init",
            )
            ok(c.robot_connect(True), "connect")
            power = c.robot_power(True)
            ok(power, "power")
            if power.message:
                raise RuntimeError(
                    "power succeeded with a load/TCP warning; no motion is sent: "
                    + power.message
                )
            ok(c.robot_subscribe(), "subscribe")
            status = c.robot_status()
            ok(status, "status")
            state = parse_state(status)
            if not (
                state.get("connect_status")
                and state.get("power_status")
                and state.get("subscribe_status")
            ):
                raise RuntimeError("robot status does not confirm ready prerequisites")
            c.robot_pose()
            ok(
                c.robot_move_step(step["move_type"], step["direction"], step["speed"]),
                "move_step",
            )
            ok(c.robot_stop(), "move_stop")
            stopped = c.robot_status()
            ok(stopped, "status_after_stop")
            if parse_state(stopped).get("motion_status") not in (0, False):
                raise RuntimeError(
                    "move_stop accepted but motion status is not confirmed idle"
                )
    except (ApiError, ValueError, RuntimeError, TypeError, KeyError) as e:
        print(f"SDK error: {e}; raw={getattr(e, 'raw', None)!r}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
