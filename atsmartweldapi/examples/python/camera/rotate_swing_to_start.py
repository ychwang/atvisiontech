#!/usr/bin/env python3
"""旋转到开始位置。"""

from _common import camera_client, call, check_swing_angle, require_ready


# 涉及连接中断、激光、电机、采图或设备控制；确认现场条件后改为True。
READY = False


if __name__ == "__main__":
    require_ready(READY)
    with camera_client() as client:
        info = call(client, {"command_type": "get_swing_motor_info"})["data"]
        angle = call(client, {"command_type": "get_swing_cur_angle"})["data"]
        check_swing_angle(angle, info)
        call(client, {"command_type": "rotate_swing_to_start"})
