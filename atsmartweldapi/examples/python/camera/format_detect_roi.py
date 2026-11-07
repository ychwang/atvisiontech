#!/usr/bin/env python3
"""获取SDK格式化后的默认ROI。

驱动只格式化内部默认ROI，不读取请求ROI。前后回读核对是否改变相机配置。"""

from _common import camera_client, call, check_equal, require_ready


# 涉及连接中断、激光、电机、采图或设备控制；确认现场条件后改为True。
READY = False


if __name__ == "__main__":
    require_ready(READY)
    with camera_client() as client:
        before = call(client, {"command_type": "get_camera_config"})["camera_config"]
        call(client, {"command_type": "format_detect_roi"})
        after = call(client, {"command_type": "get_camera_config"})["camera_config"]
        for key in ("left_roi", "right_roi"):
            check_equal(after[key], before[key])
