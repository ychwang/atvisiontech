#!/usr/bin/env python3
"""读取已连接的 3D 相机配置。"""

import json
import os
from pathlib import Path
from aotai_sdk import Client


if __name__ == "__main__":
    # 随包 XML 已填写：系统主机 192.168.1.101，本机网卡 192.168.1.252。
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

    with Client() as client:
        request = {"command_type": "get_camera_config"}
        response = client.camera_config(json.dumps(request), timeout=15)
        config = json.loads(response.message)
        print(json.dumps(config, ensure_ascii=False, indent=2))
