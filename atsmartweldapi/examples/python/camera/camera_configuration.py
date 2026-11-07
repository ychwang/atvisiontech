#!/usr/bin/env python3
"""读取帧率 → 修改1帧 → 回读验证 → 恢复原值并验证。"""

from _common import camera_client, call, check_equal, exact_integer


if __name__ == "__main__":
    with camera_client() as client:
        current = call(client, {"command_type": "get_camera_config"})["camera_config"]
        limits = call(client, {"command_type": "get_param_range"})["ranges"]["frame_rate"]
        before = exact_integer(current["frame_rate"])
        target = before - 1 if before > limits["min"] else before + 1
        if not limits["min"] <= before <= limits["max"] or not limits["min"] <= target <= limits["max"]:
            raise ValueError("设备帧率范围内没有可用的相邻测试值。")
        print(f"修改前 frame_rate = {before}；准备设置为 {target}", flush=True)
        try:
            call(client, {"command_type": "camera_configuration", "camera_config": {"frame_rate": target}})
            actual = call(client, {"command_type": "get_camera_config"})["camera_config"]
            check_equal(actual["frame_rate"], target)
            print(f"修改后 frame_rate = {actual['frame_rate']}，验证通过", flush=True)
        finally:
            call(client, {"command_type": "camera_configuration", "camera_config": {"frame_rate": before}})
            restored = call(client, {"command_type": "get_camera_config"})["camera_config"]
            check_equal(restored, current)
            print(f"已恢复 frame_rate = {restored['frame_rate']}，完整配置核对通过", flush=True)
