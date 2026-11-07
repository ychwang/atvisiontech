#!/usr/bin/env python3
"""读取RGB自动曝光阈值。"""

from _common import run


if __name__ == "__main__":
    run({"command_type": "get_rgb_auto_expose_thres"})
