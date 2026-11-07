#!/usr/bin/env python3
"""禁用摆动电机。"""

from _common import camera_client, call, check_equal, require_ready


# 涉及连接中断、激光、电机、采图或设备控制；确认现场条件后改为True。
READY = False


if __name__ == "__main__":
    require_ready(READY)
    with camera_client() as client:
        call(client, {"command_type": "disable_swing_motor"})
        check_equal(call(client, {"command_type": "is_enable_swing_motor"})["data"], False)
