#!/usr/bin/env python3
"""单台3D相机：连接 → 设置 → 单次扫描 → 读取点云 → 关灯、关罩、停机。

直接运行，无命令行参数。只由本程序控制相机；不要同时运行APP预览或其他采集程序。
参数来自 2026-11-05 15:41 的成功扫描。详细说明见 camera_scan_demo.md。
"""

import json
from pathlib import Path
from queue import Empty, Queue
import time
from datetime import datetime

from _common import camera_client, call, check_equal

GUID = "a397a255-53be-41fc-996b-521413e9e22d"
CAMERA_CONFIG = {
    "exposure": 600, "exposure_mode": "fixed", "frame_rate": 200,
    "left_gain": 1, "right_gain": 1,
    "left_roi": {"left": 0, "right": 1216, "top": 0, "bottom": 1920},
    "right_roi": {"left": 0, "right": 1216, "top": 0, "bottom": 1920},
}
LASER_POWER = 3
SWING_START, SWING_END, SWING_SPEED = 0, 60, 50
SCAN_TIMEOUT = 45                      # 等待单次扫描完成，超时不下载旧缓存。
DOWNLOAD_TIMEOUT = 60
OUTPUT_ROOT = Path(__file__).resolve().parent / "scan_results"


def control(client, command):
    result = json.loads(client.camera_control(
        json.dumps({"command_type": command}), timeout=15
    ).message)
    print(f"控制 {command}: {result}", flush=True)
    check_equal(result.get("status"), 200)
    if result.get("error_type") not in (None, 0):
        raise RuntimeError(f"控制失败：{result}")
    return result


def wait_for_scan(events):
    """状态Topic确认开始和结束；服务200本身不是扫描完成。"""
    started = False
    deadline = time.monotonic() + SCAN_TIMEOUT
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("扫描等待超时；状态未知，不下载点云。")
        try:
            raw = events.get(timeout=remaining)
        except Empty:
            raise TimeoutError("未收到完整的扫描开始→结束通知；状态未知，不下载点云。")
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise RuntimeError(f"状态通知不是JSON对象：{event}")
        if event.get("event_type") != "capture":
            continue
        if type(event.get("status")) is not int or event["status"] not in (0, 1):
            raise RuntimeError(f"无法识别的采集状态：{event}")
        print("采集状态：", event, flush=True)
        if event.get("status") == 1:
            if started:
                raise RuntimeError("重复开始通知，可能有其他客户端控制相机。")
            started = True
        elif event.get("status") == 0:
            count = event.get("point_cloud_count")
            if not started or type(count) is not int or count <= 0:
                raise RuntimeError(f"没有完整扫描或没有有效点云：{event}")
            return count


def download(client, partial, expected_points):
    count, blocks, preview = 0, 0, []
    with partial.open("w", encoding="utf-8") as output:
        def sink(sequence, total, cloud):
            nonlocal count, blocks
            points = [{key: getattr(p, key) for key in ("x", "y", "z", "w", "p", "r")}
                      for p in cloud.points]
            output.write(json.dumps({"sequence_id": sequence, "total_blocks": total,
                                     "timestamp": cloud.timestamp, "points": points},
                                    ensure_ascii=False, allow_nan=False) + "\n")
            preview.extend(points[:max(0, 3 - len(preview))])
            count += len(points)
            blocks += 1
        handle = client.download_cloud('{"frequency":30}', sink)
        try:
            handle.wait_result(DOWNLOAD_TIMEOUT)  # SDK检查分块序号、完整性和Action终态。
        except BaseException:
            try:
                handle.cancel()
            except Exception as error:
                print(f"取消下载失败：{error}", flush=True)
            finally:
                handle.release()
            raise
    check_equal(count, expected_points)
    return {"points": count, "blocks": blocks, "first_points": preview}


def scan(client, message_type, folder):
    def config(command, **fields):
        return call(client, {"command_type": command, **fields})

    print("1. 连接3D相机", flush=True)
    config("connect", guid=GUID)
    check_equal(config("connect_status")["connect_status"], 1)
    # 校验要下发的扫描端点和速度。当前编码器读数与配置端点未确认同一零点，
    # 不将它换算成目标位置，也不拿它与 nMaxAngle 直接比较。
    info = config("get_swing_motor_info")["data"]
    if not 0 <= SWING_START < SWING_END <= info["nMaxAngle"] <= info["nMotorMaxAngle"]:
        raise ValueError(f"扫描端点超出设备报告的配置范围：{info}")
    if not info["nMinSpeed"] <= SWING_SPEED <= info["nMaxSpeed"]:
        raise ValueError(f"扫描速度超出设备报告的范围：{info}")
    ranges = config("get_param_range")["ranges"]
    for field, range_name in (("exposure", "expose"), ("frame_rate", "frame_rate")):
        limits = ranges[range_name]
        if not limits["min"] <= CAMERA_CONFIG[field] <= limits["max"]:
            raise ValueError(f"{field}超出设备当前范围：{limits}")
    laser = config("get_laser_config")["laser_config"]
    if not max(1, laser["laser_power_range"]["min"]) <= LASER_POWER <= laser["laser_power_range"]["max"]:
        raise ValueError("激光功率须为设备允许的非零等级。")
    original_strobe = config("is_enable_strobe")["data"]
    original_cover = config("is_enable_auto_cover_control")["data"]
    events = Queue()
    subscription = client.subscribe(message_type, "/at/camera_node/status", lambda m: events.put(m.data))
    partial = folder / "cloud.ndjson.partial"
    try:
        control(client, "stop_capture_image")
        control(client, "stop_capture")
        print("2. 写入成功扫描的相机、激光和摆动参数", flush=True)
        config("camera_configuration", camera_config=CAMERA_CONFIG)
        config("laser_configuration", laser_config={"laser_off": True, "laser_power_level": LASER_POWER})
        config("enable_swing_motor")
        config("set_swing_scan_mode", scan_mode=1)
        config("set_swing_rotate_direct", rotate_direct=0)
        config("set_swing_angle_speed", angle_speed=SWING_SPEED)
        config("set_swing_stop_time", mseconds=500)
        config("set_swing_motor_work_range", near_distance=300.0, far_distance=800.0)
        config("set_swing_motor_angle", start_pos=SWING_START, end_pos=SWING_END)

        print("3. 回读最终参数；工作距离设置后 ROI 可能被设备调整", flush=True)
        configured = config("get_camera_config")["camera_config"]
        for key in ("exposure", "exposure_mode", "frame_rate", "left_gain", "right_gain"):
            check_equal(configured[key], CAMERA_CONFIG[key])
        check_equal(config("get_swing_scan_mode")["data"], 1)
        check_equal(config("get_swing_rotate_direct")["data"], 0)
        check_equal(config("get_swing_angle_speed")["data"], SWING_SPEED)
        check_equal(config("get_swing_motor_angle")["data"],
                    {"start_pos": SWING_START, "end_pos": SWING_END})
        check_equal(config("is_enable_swing_motor")["data"], True)
        check_equal(config("get_laser_config")["laser_config"]["laser_power_level"], LASER_POWER)
        print("4. 启动单次扫描，由扫描驱动控制激光和自动保护盖", flush=True)
        while not events.empty():
            events.get_nowait()  # 丢弃本次启动之前的停采通知。
        control(client, "start_capture")
        expected = wait_for_scan(events)
        control(client, "stop_capture")
        print(f"5. 扫描结束，设备报告{expected}个点；下载并核对", flush=True)
        result = download(client, partial, expected)
        result["configured_camera"] = configured
        result["camera_after_capture"] = config("get_camera_config")["camera_config"]
    finally:
        print("6. 停采、关激光、关罩、禁用电机；保留本次扫描参数", flush=True)
        # 一步失败仍尝试后续清理；任何失败均不能宣称完成。
        errors = []
        actions = [
            lambda: control(client, "stop_capture"),
            lambda: control(client, "stop_capture_image"),
            lambda: control(client, "close_laser"),
            lambda: config("disable_swing_motor"),
            # C版手动灯开关仅在频闪禁用时有效；关闭后恢复原频闪模式。
            lambda: config("enable_strobe", enable=False),
            lambda: config("turn_on_strobe_laser", on=False),
            lambda: control(client, "close_cover"),
            lambda: config("enable_strobe", enable=original_strobe),
            lambda: config("enable_auto_cover_control", enable=original_cover),
            lambda: check_equal(config("is_enable_swing_motor")["data"], False),
            lambda: check_equal(config("laser_status")["laser_status"], False),
            lambda: check_equal(config("is_turn_on_strobe_laser")["data"], False),
            lambda: check_equal(config("is_enable_strobe")["data"], original_strobe),
            lambda: check_equal(config("is_enable_auto_cover_control")["data"], original_cover),
        ]
        for action in actions:
            try:
                action()
            except Exception as error:
                errors.append(str(error))
                print(f"清理/恢复失败：{error}", flush=True)
        subscription.release()
        if errors:
            raise RuntimeError("清理未完成，设备状态需核对：" + "; ".join(errors))
    # 只有扫描、下载、点数核对、清理全部通过，才生成最终结果文件。
    final = folder / "cloud.ndjson"
    partial.replace(final)
    result.update(file=str(final), status="passed", frame="未由接口提供", unit="未由接口提供",
                  note="VZ点的w/p/r存放RGB，不是欧拉角；本例没有移动机器人。")
    (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    with camera_client() as client:
        from std_msgs.msg import String
        folder = OUTPUT_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        folder.mkdir(parents=True)
        result = scan(client, String, folder)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"未完成：{error}；raw={getattr(error, 'raw', None)!r}", flush=True)
        raise SystemExit(1)
