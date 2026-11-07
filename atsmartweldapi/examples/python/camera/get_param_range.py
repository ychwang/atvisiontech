#!/usr/bin/env python3
"""读取设备参数范围。"""

from _common import run


if __name__ == "__main__":
    run({"command_type": "get_param_range"})
