#!/usr/bin/env python3
"""搜索 3D 相机并打印设备信息；使用 --search 显式开启搜索。"""

import argparse
import json
import math
import threading


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search", action="store_true", help="开启相机搜索")
    parser.add_argument("--seconds", type=float, default=10, help="等待结果的秒数，默认 10")
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error("--seconds 必须是有限正数")
    if not args.search:
        print("离线模式：添加 --search 开启搜索，例如 --search --seconds 10")
        return 0

    from aotai_sdk import Client
    from std_msgs.msg import String

    found = threading.Event()

    def receive(message):
        if found.is_set():
            return
        try:
            devices = json.loads(message.data)
            if not isinstance(devices, list) or any(
                not isinstance(device, dict) for device in devices
            ):
                raise ValueError("预期为设备对象数组")
        except (ValueError, TypeError) as error:
            print(f"发现消息格式异常：{error}；原文={message.data!r}", flush=True)
            return
        if devices:
            print(f"发现 {len(devices)} 个设备：", flush=True)
            print(json.dumps(devices, ensure_ascii=False, indent=2), flush=True)
            found.set()

    with Client() as client:
        # 先订阅结果，再开启搜索。
        client.subscribe(String, "/at/camera_node/sensor_search_result", receive)
        try:
            client.camera_search(True)
            print(f"搜索已开启，最多等待 {args.seconds:g} 秒。", flush=True)
            if not found.wait(args.seconds):
                print("未收到设备列表，不能直接判定没有设备。")
                return 3
        finally:
            # 正常结束、超时或中断，都尝试关闭搜索。
            client.camera_search(False)
            print("搜索已关闭。", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
