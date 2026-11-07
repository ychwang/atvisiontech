#!/usr/bin/env python3
"""写入RGB曝光值。

先读取当前值，再原值写回并回读核对。
本示例按仓库 VZNL_RGBConfig.h 标注的20..100000范围检查；部署SDK不同须先核对。
实测曾回读145939，超出该范围时停止写入，不能擅自截断后声称可恢复。"""

from _common import camera_client, call, check_equal, exact_integer


if __name__ == "__main__":
    with camera_client() as client:
        value = call(client, {"command_type": "get_rgb_expose"})["data"]
        value = exact_integer(value)
        if not 20 <= value <= 100000:
            raise ValueError(f"RGB曝光回读{value}超出仓库SDK标注的20..100000，请先核对部署SDK。")
        request = {"command_type": "set_rgb_expose", "rgb_expose": value}
        call(client, request)
        actual = call(client, {"command_type": "get_rgb_expose"})["data"]
        check_equal(actual, request["rgb_expose"])
