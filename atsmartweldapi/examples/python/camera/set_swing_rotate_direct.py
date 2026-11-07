#!/usr/bin/env python3
"""写入摆动方向。

先读取当前值，再原值写回并回读核对；要修改值时编辑 request。"""

from _common import camera_client, call, check_equal, exact_integer, require_ready


# 涉及连接中断、激光、电机、采图或设备控制；确认现场条件后改为True。
READY = False


if __name__ == "__main__":
    require_ready(READY)
    with camera_client() as client:
        value = call(client, {"command_type": "get_swing_rotate_direct"})["data"]
        value = exact_integer(value)
        request = {"command_type": "set_swing_rotate_direct", "rotate_direct": value}
        call(client, request)
        actual = call(client, {"command_type": "get_swing_rotate_direct"})["data"]
        check_equal(actual, request["rotate_direct"])
