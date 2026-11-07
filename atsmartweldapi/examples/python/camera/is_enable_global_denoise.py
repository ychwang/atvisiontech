#!/usr/bin/env python3
"""读取全局降噪状态。"""

from _common import run


if __name__ == "__main__":
    run({"command_type": "is_enable_global_denoise"})
