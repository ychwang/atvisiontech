#!/usr/bin/env python3
"""读取激光器停止位置。"""

from _common import run


if __name__ == "__main__":
    run({"command_type": "get_swing_stop_angle"})
