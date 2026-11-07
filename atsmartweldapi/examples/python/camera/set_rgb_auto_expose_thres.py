#!/usr/bin/env python3
"""写入RGB自动曝光阈值。

先读取当前值，再原值写回并回读核对；要修改值时编辑 request。"""

from _common import camera_client, call, check_equal


if __name__ == "__main__":
    with camera_client() as client:
        value = call(client, {"command_type": "get_rgb_auto_expose_thres"})["data"]
        request = {"command_type": "set_rgb_auto_expose_thres", "rgb_auto_expose_thres": value}
        call(client, request)
        actual = call(client, {"command_type": "get_rgb_auto_expose_thres"})["data"]
        check_equal(actual, request["rgb_auto_expose_thres"])
