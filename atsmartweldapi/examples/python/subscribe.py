#!/usr/bin/env python3
"""Read one real status/feedback Topic for a bounded interval.

Default is offline. --connect only subscribes; it sends no device command.
Use --prefix only with an isolated mock namespace (for example /api_sdk_mock).
Supported names map directly to the endpoint catalogue: robot, welder, task,
camera-status, and camera-points.
"""

import argparse
import math
import threading

from aotai_sdk import Client, CommunicationError

parser = argparse.ArgumentParser()
parser.add_argument(
    "--connect", action="store_true", help="open a read-only subscription"
)
parser.add_argument(
    "--topic",
    choices=("robot", "welder", "task", "camera-status", "camera-points"),
    default="robot",
)
parser.add_argument("--seconds", type=float, default=10.0)
parser.add_argument("--prefix", default="", help="isolated mock namespace only")
args = parser.parse_args()

if not math.isfinite(args.seconds) or args.seconds <= 0:
    parser.error("--seconds must be a finite positive number")
if not args.connect:
    print(
        "Offline: pass --connect to subscribe for up to 10 seconds; no device command was sent."
    )
    raise SystemExit(0)

# Import generated ROS messages only on the explicit ROS path.
if args.topic == "robot":
    from weld_interfaces.msg import ATRobotStatus as Message

    topic = "/at/robot/get_real_time_status"

    def describe(msg):
        return {
            "robot_mode": msg.robot_mode,
            "connect_status": msg.connect_status,
            "timestamp": msg.timestamp,
        }

elif args.topic == "welder":
    from weld_interfaces.msg import ATWelderRealTimeData as Message

    topic = "/at/welder/welder_realtime_data"

    def describe(msg):
        return {
            "enable": msg.enable,
            "real_time_voltage": msg.real_time_voltage,
            "real_time_current": msg.real_time_current,
            "timestamp": msg.timestamp,
        }

elif args.topic == "task":
    from std_msgs.msg import String as Message

    topic = "/at/task/task_feedback"

    def describe(msg):
        return {"data": msg.data}

elif args.topic == "camera-status":
    from std_msgs.msg import String as Message

    topic = "/at/camera_node/status"

    def describe(msg):
        return {"data": msg.data}

else:
    from weld_interfaces.msg import ATPointCloud as Message

    topic = "/at/camera_node/points_raw"

    def describe(msg):
        return {"timestamp": msg.timestamp, "point_count": len(msg.points)}


received = threading.Event()
try:
    with Client(endpoint_prefix=args.prefix) as client:

        def callback(message):
            print(describe(message), flush=True)
            received.set()

        subscription = client.subscribe(Message, topic, callback)
        try:
            if not received.wait(args.seconds):
                raise CommunicationError(
                    f"no message on {topic} within {args.seconds:g}s; check publisher/namespace"
                )
        finally:
            subscription.release()
except Exception as exc:
    print(f"subscription failed: {exc}")
    raise SystemExit(3)
print("received one read-only message; subscription released")
