# 最小 C++ ROS 2 接入 Demo（只读）

这个 C++17 / ROS 2 Humble 示例默认只调用 `/at/robot/status`，不会运动、起弧、下发作业或连接焊机。

## 接口

- 服务：`/at/robot/status`，类型为 `weld_interfaces/srv/ATStringGeneric`。
- 请求：`string id` 和 `string data`。Demo 固定 `id=""`、默认 `data="robot_status"`。
- 响应：`int16 status`、`string data`、`string message`。`status == 200` 时程序以成功状态退出。
- `data` 是 JSON 字符串，Demo 原样打印；调用方应按机器人状态接口说明解析实际返回字段。

## 从 API 根目录构建

本交付已包含 `interfaces/weld_interfaces`。先构建消息包并加载生成类型：

```bash
source /opt/ros/humble/setup.bash
colcon build --base-paths interfaces/weld_interfaces --cmake-args -DBUILD_TESTING=OFF
source install/setup.bash
```

再用普通 CMake 构建最小 Demo：

```bash
cmake -S examples/cpp/ros2_demo -B build/raw-demo -DBUILD_SDK_DEMO=OFF -DBUILD_TESTING=OFF
cmake --build build/raw-demo -j2
```

配置好与服务端一致的 ROS domain，并确认 DDS 网络可达后运行：

```bash
export ROS_DOMAIN_ID=0  # 示例值；按部署配置修改
export ROS_LOCALHOST_ONLY=0
./build/raw-demo/aotai_ros2_raw_query
```

程序自行初始化 rclcpp、创建节点和客户端、等待服务、发送一次异步请求，并使用 `SingleThreadedExecutor` 等待响应。`service_timeout_ms` 限制服务发现时间，`response_timeout_ms` 限制响应等待时间；超时后不会自动重发。

退出码 0 表示业务状态成功，2 表示服务端返回业务失败，3 表示通信失败或超时，64 表示本地参数错误。

## SDK Demo（可选）

一次构建接口包与 C++ SDK，然后启用 SDK target：

```bash
source /opt/ros/humble/setup.bash
colcon build --base-paths interfaces/weld_interfaces sdk/cpp --cmake-args -DBUILD_TESTING=OFF
source install/setup.bash
cmake -S examples/cpp/ros2_demo -B build/sdk-demo -DBUILD_SDK_DEMO=ON -DBUILD_TESTING=OFF
cmake --build build/sdk-demo -j2
./build/sdk-demo/aotai_ros2_sdk_query --connect
```

`aotai_sdk::Client` 管理自己的 ROS Context、节点和执行器线程。`--connect` 是显式联网开关；不带该参数时只打印用法。`--topic` 可额外订阅 `/at/robot/get_real_time_status`，收到一条消息后释放订阅并退出。

Action、作业控制和点云示例分别位于相邻的 `multipass.cpp`、`control.cpp` 和 `camera_cloud.cpp`，不会由本 Demo 自动执行。
