#!/usr/bin/env python3
"""读取RGB自动白平衡状态。"""

from _common import run


if __name__ == "__main__":
    run({"command_type": "is_enable_rgb_awb"})
