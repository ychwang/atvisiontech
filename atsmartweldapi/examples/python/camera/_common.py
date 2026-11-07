"""相机示例共用的 DDS 配置、请求发送和错误检查。导入时不连接设备。"""

import json
import math
import os
from pathlib import Path


def camera_client():
    # 系统主机 192.168.1.101、本机网卡 192.168.1.252；换机器时修改 XML。
    os.environ.update(
        ROS_DOMAIN_ID="0",
        ROS_LOCALHOST_ONLY="0",
        RMW_IMPLEMENTATION="rmw_fastrtps_cpp",
        FASTRTPS_DEFAULT_PROFILES_FILE=str(
            Path(__file__).resolve().parents[2] / "config/fastdds_client.xml"
        ),
    )
    os.environ.pop("ROS_DISCOVERY_SERVER", None)
    os.environ.pop("FASTDDS_DEFAULT_PROFILES_FILE", None)
    from aotai_sdk import Client

    return Client()


def require_ready(ready):
    if not ready:
        raise SystemExit("尚未发送：请确认脚本中的现场条件和参数，再将 READY 改为 True。")


def check_request(request):
    """缺少真实参数时在本机终止，不能把 None/NaN 交给驱动转换成 0。"""
    def check(value):
        if value is None:
            raise ValueError("请先在脚本中填写真实参数，不能发送 None。")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("参数必须是有限数值。")
        if isinstance(value, dict):
            for item in value.values():
                check(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                check(item)

    if not isinstance(request, dict) or not request.get("command_type"):
        raise ValueError("请求必须包含 command_type。")
    check(request)


def call(client, request):
    """只发一次请求，不自动重试。返回 message 解析后的字典。"""
    check_request(request)
    try:
        response = client.camera_config(json.dumps(request, allow_nan=False), timeout=15)
    except Exception as error:
        print(f"调用失败：{error}；raw={getattr(error, 'raw', None)!r}", flush=True)
        raise
    result = json.loads(response.message)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    if not isinstance(result, dict) or type(result.get("status")) is not int:
        raise RuntimeError("响应缺少整数 status。")
    # 驱动 ROI 错误可能仍返回 status=200，因此还要检查 error_type。
    if result["status"] != 200 or result.get("error_type") not in (None, 0):
        raise RuntimeError(f"设备返回失败：{result}")
    if request["command_type"] in ("enable_global_denoise", "disable_global_denoise"):
        if type(result.get("data")) is not int or result["data"] != 0:
            raise RuntimeError(f"降噪 SDK 调用失败或缺少返回码：{result}")
    check_response(request["command_type"], result)
    return result


def run(request):
    check_request(request)
    with camera_client() as client:
        return call(client, request)


def check_equal(actual, expected):
    if actual != expected:
        raise RuntimeError(f"回读不一致：期望 {expected!r}，实际 {actual!r}")


def exact_integer(value):
    """兼容整数形式的浮点回读；拒绝驱动 toInt 会截断的小数。"""
    if type(value) not in (int, float) or not math.isfinite(value) or int(value) != value:
        raise ValueError(f"当前接口只接受整数，不能无损写回 {value!r}。")
    return int(value)


def check_swing_angle(angle, info):
    """只使用设备报告的角度范围；读数异常时不猜测换算、不发送动作。"""
    values = [angle] + [info.get(key) for key in (
        "nMotorMaxAngle", "nMaxAngle", "nStartAngle", "nEndAngle"
    )]
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise ValueError("摆动角度及设备范围必须是有限数值。")
    _, motor_max, maximum, start, end = values
    if not 0 < maximum <= motor_max or not 0 <= start <= end <= maximum:
        raise ValueError(f"设备返回的摆动范围无效：{info}")
    if not 0 <= angle <= maximum:
        raise ValueError(
            f"当前角度数值 {angle} 超出配置角度上限 {maximum}，无法确认动作条件。"
            "需核对SDK读取错误码及两种角度的零点定义；未发送位置/扫描动作，不能直接除10或减360。"
        )
    return angle


def check_points(points):
    if not isinstance(points, list) or len(points) < 5:
        raise ValueError("需要至少 5 组真实标定样本；请填写脚本中的列表。")
    for point in points:
        if not isinstance(point, list) or len(point) != 6:
            raise ValueError("每组标定样本必须是 6 个数。")
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in point):
            raise ValueError("标定样本必须是有限数值，不能含 None/布尔值。")


def check_response(command, result):
    """检查查询结果的必要字段；200 加空对象不能算读取成功。"""
    number = (int, float)

    def field(obj, key, kinds):
        value = obj.get(key) if isinstance(obj, dict) else None
        kinds = kinds if isinstance(kinds, tuple) else (kinds,)
        if type(value) not in kinds:
            raise RuntimeError(f"{command} 响应字段 {key} 缺失或类型错误：{value!r}")
        if type(value) in number and not math.isfinite(value):
            raise RuntimeError(f"{command} 响应字段 {key} 不是有限数值。")
        return value

    def vector(value, size):
        if not isinstance(value, list) or len(value) != size or any(
            type(x) not in number or not math.isfinite(x) for x in value
        ):
            raise RuntimeError(f"{command} 应返回 {size} 个有限数值。")

    def roi(value):
        for key in ("left", "right", "top", "bottom"):
            field(value, key, int)
        if not 0 <= value["left"] < value["right"] or not 0 <= value["top"] < value["bottom"]:
            raise RuntimeError(f"{command} 返回无效 ROI：{value}")

    if command == "connect_status":
        if field(result, "connect_status", int) not in (0, 1):
            raise RuntimeError("connect_status 应为 0 或 1。")
    elif command == "get_resolution":
        for key in ("width", "height"):
            if field(result, key, int) <= 0:
                raise RuntimeError("分辨率必须为正整数。")
    elif command == "laser_status":
        field(result, "laser_status", bool)
    elif command.startswith("is_"):
        field(result, "data", bool)
    elif command in ("get_swing_motor_angle", "get_swing_motor_info"):
        data = field(result, "data", dict)
        keys = ("start_pos", "end_pos") if command == "get_swing_motor_angle" else (
            "nMotorMaxAngle", "nMaxAngle", "nMinSpeed", "nMaxSpeed", "nStartAngle",
            "nEndAngle", "nSpeed", "nStopAngle", "fEndAngleThres",
        )
        for key in keys:
            field(data, key, number)
    elif command in ("get_swing_angle_speed", "get_swing_scan_mode", "get_swing_cur_angle",
                     "get_swing_rotate_direct", "get_swing_stop_angle", "get_swing_end_angle_thres",
                     "get_rgb_expose", "get_rgb_gain", "get_rgb_trigger_mode",
                     "get_rgb_auto_expose_thres", "get_anti_reflect_gain_type"):
        integer = command not in ("get_swing_cur_angle", "get_swing_end_angle_thres", "get_rgb_auto_expose_thres")
        field(result, "data", int if integer else number)
    elif command == "get_param_range":
        ranges = field(result, "ranges", dict)
        for key in ("frame_rate", "expose", "gain", "laser_light", "frame_rate_without_color_data",
                    "frame_rate_with_color_data", "strobe_time_ratio"):
            bounds = field(ranges, key, dict)
            low, high = field(bounds, "min", int), field(bounds, "max", int)
            if not 0 <= low <= high:
                raise RuntimeError(f"参数范围无效：{key}={bounds}")
    elif command == "get_eye_hand_calib_cfg":
        config = field(result, "calib_cfg_para", dict)
        for key in ("bUseStereoCalib", "bEnableEyeToHandCalibMatrixAdjust"):
            field(config, key, bool)
        for key in ("eCalibType", "eROrder", "eCalibBoardType", "nCalibBoardLength",
                    "nCalibBoardWidth", "nEyeToHandMinCalibItemNum"):
            field(config, key, int)
        for key in ("dCalibGridEdgeLen", "dCornerDetectErrThres", "dEyeToHandMinCalilbErrThres"):
            field(config, key, number)
    elif command == "get_calib_board_extrinsic":
        vector(field(field(result, "calib_board_extrinsic", dict), "values", list), 6)
    elif command == "get_eye_hand_calib_matrix":
        vector(field(result, "calib_matrix", list), 16)
        errors = field(result, "calib_error_info", dict)
        for key in ("max_distance", "min_distance", "avg_distance"):
            field(errors, key, number)
    elif command == "get_detected_calib_board_info":
        info = field(result, "detected_calib_board_info", dict)
        if field(info, "error_code", int) != 0:
            raise RuntimeError(f"标定板检测失败：{info}")
        vector(field(info, "extrinsic", list), 6)
        field(info, "left_corners", dict)
        field(info, "right_corners", dict)
    elif command == "format_detect_roi":
        data = field(result, "data", dict)
        for key in ("left_roi", "right_roi"):
            roi(field(data, key, dict))

    if command in ("connect", "get_camera_config", "camera_configuration"):
        config = field(result, "camera_config", dict)
        if field(config, "exposure_mode", str) not in ("fixed", "auto"):
            raise RuntimeError("未知曝光模式。")
        for key in ("exposure", "frame_rate", "left_gain", "right_gain"):
            if field(config, key, int) < 0:
                raise RuntimeError(f"相机参数为负数：{key}")
        for key in ("left_roi", "right_roi"):
            roi(field(config, key, dict))
    if command in ("connect", "get_laser_config", "laser_configuration"):
        config = field(result, "laser_config", dict)
        field(config, "laser_off", bool)
        level = field(config, "laser_power_level", int)
        bounds = field(config, "laser_power_range", dict)
        if not field(bounds, "min", int) <= level <= field(bounds, "max", int):
            raise RuntimeError("激光功率不在返回的范围内。")
