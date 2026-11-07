#!/usr/bin/env python3
"""将当前位置设为开始位置。"""

from _common import camera_client, call, check_equal, check_swing_angle, exact_integer, require_ready


# 涉及连接中断、激光、电机、采图或设备控制；确认现场条件后改为True。
READY = False


if __name__ == "__main__":
    require_ready(READY)
    with camera_client() as client:
        info = call(client, {"command_type": "get_swing_motor_info"})["data"]
        angle = call(client, {"command_type": "get_swing_cur_angle"})["data"]
        angle = exact_integer(check_swing_angle(angle, info))
        positions = call(client, {"command_type": "get_swing_motor_angle"})["data"]
        call(client, {"command_type": "set_swing_cur_start_pos"})
        positions["start_pos"] = angle
        actual = call(client, {"command_type": "get_swing_motor_angle"})["data"]
        check_equal(actual, positions)
