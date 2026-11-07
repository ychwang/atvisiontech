#!/usr/bin/env python3
"""读取摆动起止位置。"""

from _common import run


if __name__ == "__main__":
    run({"command_type": "get_swing_motor_angle"})
