#!/usr/bin/env python3
"""Robot status example.

Run after sourcing ROS/weld_interfaces: python3 basic.py [--connect].  Default
prints an offline notice; --connect calls only /at/robot/status and prints its
raw server data (not a motion or readiness guarantee).
"""

import argparse
from aotai_sdk import Client

p = argparse.ArgumentParser()
p.add_argument("--connect", action="store_true")
a = p.parse_args()
if not a.connect:
    print(
        "Offline: use --connect for read-only robot status. No device command was sent."
    )
else:
    with Client() as c:
        print(c.robot_status().data)
