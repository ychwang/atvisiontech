# 最小调用 Demo

两种 Demo 都不需要安装或构建 SDK；原生方式只需 ROS 2 和 weld_interfaces，rosbridge 客户端只需 WebSocket。

两个 Demo 都只查询 `/at/robot/status`，请求为 `id=""`、`data="robot_status"`。查询返回机器人连接、电源和运行状态；Demo 不发送初始化、连接、上电或运动命令。状态查询可能刷新设备状态或触发驱动连接恢复，运行前按部署方提供的接入条件确认查询行为。

原生 ROS 2 示例使用 `weld_interfaces/srv/ATStringGeneric`：直接读取响应的 `status/data/message`。rosbridge 示例在同一请求外增加 WebSocket 消息封装：先检查桥接 `result`，再检查 `values.status`，最后解析 `values.data` 内的 JSON 字符串。下方代码完整显示并可复制。

## 方案一：原生 ROS 2，C++

客户端安装 ROS 2 Humble 和 rclcpp，加载匹配的 weld_interfaces；尚未安装接口包时从本 API 目录构建随附版本。客户端与服务端使用相同 ROS_DOMAIN_ID；跨主机时允许 DDS 发现与数据通信，ROS_LOCALHOST_ONLY 应为 0。服务名称已经包含命名空间，不再添加工控机 IP。

以下以 API 交付目录为当前目录。先构建接口包，再将 ROS_DOMAIN_ID 改为部署方提供的值：

```bash
source /opt/ros/humble/setup.bash
colcon build --base-paths interfaces/weld_interfaces --cmake-args -DBUILD_TESTING=OFF
source install/setup.bash
export ROS_DOMAIN_ID=0  # 示例值；按服务端实际配置修改
export ROS_LOCALHOST_ONLY=0
ros2 service type /at/robot/status
cmake -S examples/cpp/ros2_demo -B build/raw-demo -DBUILD_TESTING=OFF
cmake --build build/raw-demo -j2
./build/raw-demo/aotai_ros2_raw_query
```

用户自建 C++ 包可直接采用此程序，仅依赖 rclcpp/weld_interfaces；创建和构建自己的包见[构建与运行](#build-run)。

发现服务和等待响应各有 3 秒默认超时。退出码 0 表示该查询业务成功，2 表示服务端业务返回失败，3 表示通信失败或超时，64 表示本地参数错误。`data` 原样打印，集成时按机器人状态接口的字段表解析其中 JSON。

## 方案二：rosbridge，JavaScript / WebSocket

浏览器或 Node.js 22+ 直接连接部署方提供的 `ws://` 或 `wss://` 地址。客户端无需安装 ROS；桥接端需已加载匹配的接口包，并能够发现 `/at/robot/status`。WebSocket 连接成功只表明桥接连接建立，服务调用还可能失败。

下面的 `ws://127.0.0.1:9090` 是本机示例地址。远程接入应替换为实际桥接 IP、端口及路径；9090 是常见默认端口，实际值由部署方提供。HTTPS 页面使用可受信任的 `wss://` 地址，避免浏览器混合内容限制。

复制完整 JavaScript 到浏览器开发者工具 Console 执行，或保存为 `robot_status_rosbridge.js` 后运行：

```bash
node --input-type=commonjs < examples/javascript/robot_status_rosbridge.js
```

程序只发送一次查询，5 秒内未收到对应响应即结束并关闭客户端连接。外层 `id` 用于匹配当前桥接响应；`args.id` 是 ROS 请求字段，本接口留空。无关响应不会当作当前查询结果；网络错误、桥接失败、业务失败及 JSON 解析失败分别报错，均不自动重发。

成功时打印实际收到的机器人状态对象。这里不预填设备状态或成功结果；运行前需已有可访问的查询服务。关闭客户端连接只释放通信资源。
