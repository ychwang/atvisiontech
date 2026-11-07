#!/usr/bin/env python3
"""关闭全局降噪。

读取原状态，切换并核对，完成后恢复原状态。SDK data必须为0才算调用成功。"""

from _common import camera_client, call, check_equal


if __name__ == "__main__":
    with camera_client() as client:
        original = call(client, {"command_type": "is_enable_global_denoise"})["data"]
        if type(original) is not bool:
            raise ValueError("回读值不是布尔值，停止写入。")
        call(client, {"command_type": "disable_global_denoise"})
        try:
            actual = call(client, {"command_type": "is_enable_global_denoise"})["data"]
            check_equal(actual, False)
        finally:
            restore = "enable_global_denoise" if original else "disable_global_denoise"
            call(client, {"command_type": restore})
            check_equal(call(client, {"command_type": "is_enable_global_denoise"})["data"], original)
