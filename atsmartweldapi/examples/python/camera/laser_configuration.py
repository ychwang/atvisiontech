#!/usr/bin/env python3
"""写入激光开关和功率。

先确认激光路径安全；原值写回激光开关和功率，再核对配置。"""

from _common import camera_client, call, check_equal, require_ready


# 涉及连接中断、激光、电机、采图或设备控制；确认现场条件后改为True。
READY = False


if __name__ == "__main__":
    require_ready(READY)
    with camera_client() as client:
        current = call(client, {"command_type": "get_laser_config"})["laser_config"]
        config = {key: current[key] for key in ("laser_off", "laser_power_level")}
        # laser_off=True 关闭激光；False 开启激光。
        call(client, {"command_type": "laser_configuration", "laser_config": config})
        actual = call(client, {"command_type": "get_laser_config"})["laser_config"]
        check_equal({key: actual[key] for key in config}, config)
