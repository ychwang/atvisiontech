#!/usr/bin/env python3
"""根据真实样本计算手眼标定矩阵。

计算接口，需要真实采样；空列表在本机拒绝，不能用虚构零点试真机。"""

from _common import run, check_points


# 填写至少5组成对真实样本；每个样本6个数，顺序/单位须与标定配置一致。
CAMERA_POINTS = []
ROBOT_POINTS = []


if __name__ == "__main__":
    check_points(CAMERA_POINTS)
    check_points(ROBOT_POINTS)
    if len(CAMERA_POINTS) != len(ROBOT_POINTS):
        raise ValueError("相机和机器人样本必须逐项对应、数量相同。")
    request = {
        "command_type": "get_eye_hand_calib_matrix",
        "nPointNum": len(CAMERA_POINTS),
        "pExtrinsicList": CAMERA_POINTS,
        "pRobotPointList": ROBOT_POINTS,
    }
    run(request)
