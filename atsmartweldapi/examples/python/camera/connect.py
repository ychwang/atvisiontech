#!/usr/bin/env python3
"""连接已发现的相机。

GUID 来自本次环境的搜索结果；换相机时先运行 camera_search.py。已连接时不会切换设备。"""

from _common import run


GUID = "a397a255-53be-41fc-996b-521413e9e22d"


if __name__ == "__main__":
    run({"command_type": "connect", "guid": GUID})
