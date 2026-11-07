#!/usr/bin/env python3
"""写入RGB触发模式。

先启用 RGB，修改触发模式并回读；结束时恢复原模式和 RGB 使能状态。"""

from _common import camera_client, call, check_equal, exact_integer


if __name__ == "__main__":
    with camera_client() as client:
        enabled = call(client, {"command_type": "is_enable_rgb"})["data"]
        value = call(client, {"command_type": "get_rgb_trigger_mode"})["data"]
        value = exact_integer(value)
        if value not in (0, 1, 2, 3, 4, 6, 9, 10):
            raise ValueError(f"无法恢复未知触发模式：{value}")
        # 0=被动触发，1=主动触发；选择与原值不同的模式。
        target = 0 if value == 1 else 1
        print(f"修改前 rgb_trigger_mode = {value}；准备设置为 {target}", flush=True)
        try:
            call(client, {"command_type": "enable_rgb", "enable": True})
            check_equal(call(client, {"command_type": "is_enable_rgb"})["data"], True)
            call(client, {"command_type": "set_rgb_trigger_mode", "rgb_trigger_mode": target})
            actual = call(client, {"command_type": "get_rgb_trigger_mode"})["data"]
            check_equal(actual, target)
            print(f"修改后 rgb_trigger_mode = {actual}，验证通过", flush=True)
        finally:
            try:
                call(client, {"command_type": "set_rgb_trigger_mode", "rgb_trigger_mode": value})
                restored = call(client, {"command_type": "get_rgb_trigger_mode"})["data"]
                check_equal(restored, value)
                print(f"已恢复 rgb_trigger_mode = {restored}", flush=True)
            finally:
                call(client, {"command_type": "enable_rgb", "enable": enabled})
                check_equal(call(client, {"command_type": "is_enable_rgb"})["data"], enabled)
                print(f"已恢复 RGB 使能 = {enabled}", flush=True)
