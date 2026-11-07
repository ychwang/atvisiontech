#!/usr/bin/env python3
"""写入RGB增益。

先读取当前值，再原值写回并回读核对；要修改值时编辑 request。"""

from _common import camera_client, call, check_equal, exact_integer


if __name__ == "__main__":
    with camera_client() as client:
        value = call(client, {"command_type": "get_rgb_gain"})["data"]
        value = exact_integer(value)
        request = {"command_type": "set_rgb_gain", "rgb_gain": value}
        call(client, request)
        actual = call(client, {"command_type": "get_rgb_gain"})["data"]
        check_equal(actual, request["rgb_gain"])
