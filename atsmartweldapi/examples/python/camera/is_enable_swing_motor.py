#!/usr/bin/env python3
"""读取摆动电机使能状态。"""

from _common import run


if __name__ == "__main__":
    run({"command_type": "is_enable_swing_motor"})
