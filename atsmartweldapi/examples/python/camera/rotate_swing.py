#!/usr/bin/env python3
"""旋转到指定角度。

先读取当前值，再原值写回并回读核对；要修改值时编辑 request。"""

from _common import camera_client, call, check_equal, check_swing_angle, require_ready


# 涉及连接中断、激光、电机、采图或设备控制；确认现场条件后改为True。
READY = False


if __name__ == "__main__":
    require_ready(READY)
    with camera_client() as client:
        info = call(client, {"command_type": "get_swing_motor_info"})["data"]
        value = call(client, {"command_type": "get_swing_cur_angle"})["data"]
        check_swing_angle(value, info)
        request = {"command_type": "rotate_swing", "angle": value}
        check_swing_angle(request["angle"], info)
        call(client, request)
        actual = call(client, {"command_type": "get_swing_cur_angle"})["data"]
        check_equal(actual, request["angle"])
