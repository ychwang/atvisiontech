#!/usr/bin/env python3
"""写入摆动工作距离范围。

填写真实工作距离；不要把None改成猜测的默认值。"""

import math

from _common import run, require_ready


# 涉及连接中断、激光、电机、采图或设备控制；确认现场条件后改为True。
READY = False
# 接口没有getter，必须先记录原值；单位与设备SDK约定一致。
NEAR_DISTANCE = None
FAR_DISTANCE = None


if __name__ == "__main__":
    require_ready(READY)
    if any(type(value) not in (int, float) or not math.isfinite(value)
           for value in (NEAR_DISTANCE, FAR_DISTANCE)):
        raise ValueError("请填写实际 NEAR_DISTANCE 和 FAR_DISTANCE，并记录原值。")
    if not 0 < NEAR_DISTANCE < FAR_DISTANCE:
        raise ValueError("工作距离必须满足 0 < near_distance < far_distance。")
    run({"command_type": "set_swing_motor_work_range",
         "near_distance": NEAR_DISTANCE, "far_distance": FAR_DISTANCE})
