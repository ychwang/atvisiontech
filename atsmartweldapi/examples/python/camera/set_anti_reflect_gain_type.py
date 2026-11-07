#!/usr/bin/env python3
"""写入抗反光增益档位。

先读取当前值，再原值写回并回读核对；要修改值时编辑 request。"""

from _common import camera_client, call, check_equal, exact_integer


if __name__ == "__main__":
    with camera_client() as client:
        value = call(client, {"command_type": "get_anti_reflect_gain_type"})["data"]
        value = exact_integer(value)
        request = {"command_type": "set_anti_reflect_gain_type", "anti_reflect_gain_type": value}
        call(client, request)
        actual = call(client, {"command_type": "get_anti_reflect_gain_type"})["data"]
        check_equal(actual, request["anti_reflect_gain_type"])
