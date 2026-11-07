#!/usr/bin/env python3
"""读取频闪状态。"""

from _common import run


if __name__ == "__main__":
    run({"command_type": "is_enable_strobe"})
