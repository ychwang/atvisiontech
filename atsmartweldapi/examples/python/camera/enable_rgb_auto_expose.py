#!/usr/bin/env python3
"""写入RGB自动曝光开关。

先读取当前值，再原值写回并回读核对；要修改值时编辑 request。"""

from _common import camera_client, call, check_equal


if __name__ == "__main__":
    with camera_client() as client:
        value = call(client, {"command_type": "is_enable_rgb_auto_expose"})["data"]
        if type(value) is not bool:
            raise ValueError("回读值不是布尔值，停止写入。")
        request = {"command_type": "enable_rgb_auto_expose", "enable": value}
        call(client, request)
        actual = call(client, {"command_type": "is_enable_rgb_auto_expose"})["data"]
        check_equal(actual, request["enable"])
