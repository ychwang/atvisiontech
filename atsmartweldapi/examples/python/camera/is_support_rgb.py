#!/usr/bin/env python3
"""查询是否支持RGB相机。"""

from _common import run


if __name__ == "__main__":
    run({"command_type": "is_support_rgb"})
