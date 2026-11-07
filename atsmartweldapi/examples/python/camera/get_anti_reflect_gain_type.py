#!/usr/bin/env python3
"""读取抗反光增益档位。"""

from _common import run


if __name__ == "__main__":
    run({"command_type": "get_anti_reflect_gain_type"})
