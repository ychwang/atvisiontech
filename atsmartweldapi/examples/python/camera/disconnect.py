#!/usr/bin/env python3
"""断开当前相机。"""

from _common import run, require_ready


# 涉及连接中断、激光、电机、采图或设备控制；确认现场条件后改为True。
READY = False


if __name__ == "__main__":
    require_ready(READY)
    run({"command_type": "disconnect"})
