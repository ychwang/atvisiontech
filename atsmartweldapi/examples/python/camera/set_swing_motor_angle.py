#!/usr/bin/env python3
"""写入摆动起止位置。

原值写回起止位置；这两个参数都必须提供。"""

from _common import camera_client, call, check_equal, exact_integer, require_ready


# 涉及连接中断、激光、电机、采图或设备控制；确认现场条件后改为True。
READY = False


if __name__ == "__main__":
    require_ready(READY)
    with camera_client() as client:
        current = call(client, {"command_type": "get_swing_motor_angle"})["data"]
        positions = {key: exact_integer(current[key]) for key in ("start_pos", "end_pos")}
        call(client, {"command_type": "set_swing_motor_angle", **positions})
        actual = call(client, {"command_type": "get_swing_motor_angle"})["data"]
        check_equal(actual, positions)
