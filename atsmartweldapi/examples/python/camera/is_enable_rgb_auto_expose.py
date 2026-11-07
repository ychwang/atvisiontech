#!/usr/bin/env python3
"""读取RGB自动曝光状态。"""

from _common import run


if __name__ == "__main__":
    run({"command_type": "is_enable_rgb_auto_expose"})
