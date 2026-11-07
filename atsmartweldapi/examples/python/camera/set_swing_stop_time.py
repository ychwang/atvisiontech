#!/usr/bin/env python3
"""写入摆动停顿时间。

填写现场确认的停顿时间；没有真实参数时不会发送。"""

from _common import run, require_ready


# 涉及连接中断、激光、电机、采图或设备控制；确认现场条件后改为True。
READY = False
# 本接口没有读取停顿时间的命令；先记录原值和恢复方案。SDK范围500..32767毫秒。
MSECONDS = None


if __name__ == "__main__":
    require_ready(READY)
    if type(MSECONDS) is not int or not 500 <= MSECONDS <= 32767:
        raise ValueError("请填写实际停顿时间 MSECONDS，范围500..32767毫秒。")
    run({"command_type": "set_swing_stop_time", "mseconds": MSECONDS})
