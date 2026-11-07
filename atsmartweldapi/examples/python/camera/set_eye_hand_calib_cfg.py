#!/usr/bin/env python3
"""写入手眼标定配置。

先读出真实标定配置，原值写回全部11个字段；不编造标定板参数。"""

from _common import camera_client, call, check_equal, require_ready


# 涉及连接中断、激光、电机、采图或设备控制；确认现场条件后改为True。
READY = False


if __name__ == "__main__":
    require_ready(READY)
    with camera_client() as client:
        config = call(client, {"command_type": "get_eye_hand_calib_cfg"})["calib_cfg_para"]
        call(client, {"command_type": "set_eye_hand_calib_cfg", "calib_cfg_para": config})
        actual = call(client, {"command_type": "get_eye_hand_calib_cfg"})["calib_cfg_para"]
        check_equal(actual, config)
