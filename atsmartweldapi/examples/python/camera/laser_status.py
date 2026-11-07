#!/usr/bin/env python3
"""读取激光使能状态。"""

from _common import run


if __name__ == "__main__":
    run({"command_type": "laser_status"})
