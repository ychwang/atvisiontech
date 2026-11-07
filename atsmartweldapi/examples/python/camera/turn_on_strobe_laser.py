#!/usr/bin/env python3
"""写入频闪激光开关。

先读取当前值，再原值写回并回读核对；要修改值时编辑 request。"""

from _common import camera_client, call, check_equal, require_ready


# 涉及连接中断、激光、电机、采图或设备控制；确认现场条件后改为True。
READY = False


if __name__ == "__main__":
    require_ready(READY)
    with camera_client() as client:
        value = call(client, {"command_type": "is_turn_on_strobe_laser"})["data"]
        if type(value) is not bool:
            raise ValueError("回读值不是布尔值，停止写入。")
        request = {"command_type": "turn_on_strobe_laser", "on": value}
        call(client, request)
        actual = call(client, {"command_type": "is_turn_on_strobe_laser"})["data"]
        check_equal(actual, request["on"])
