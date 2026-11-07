#!/usr/bin/env python3
"""读取保护盖自动控制状态。"""

from _common import run


if __name__ == "__main__":
    run({"command_type": "is_enable_auto_cover_control"})
