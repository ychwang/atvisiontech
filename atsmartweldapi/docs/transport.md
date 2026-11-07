# 两种接入方案

用户自建程序通过原生 ROS 2 或 rosbridge 调用系统，不需要安装或构建 SDK。两条链路使用同一组 Service、Topic 和 Action；Action 转发能力需按实际桥接版本确认。

|项目|方案一：原生 ROS 2|方案二：rosbridge / WebSocket|
|---|---|---|
|适用客户端|ROS 2 Python/C++ 应用|浏览器、桌面应用或其他可连接 WebSocket 的程序|
|通信链路|客户端 → ROS 2 / DDS → 服务端|客户端 → WebSocket → rosbridge → ROS 2 服务端|
|客户端依赖|ROS 2 Humble、rclpy/rclcpp、本交付随附的 weld_interfaces|WebSocket 客户端；浏览器已有原生 API|
|连接条件|相同 ROS_DOMAIN_ID，DDS 发现与数据通道可达；QoS 匹配|实际 ws:// 或 wss:// 地址可达；桥接端能发现目标服务并加载匹配的消息包|
|请求形式|直接构造 ROS 请求对象|在 JSON 消息 args 内传入相同请求字段|
|结果判断|检查 ROS 响应的业务字段|先检查桥接 result，再检查 values 内的业务字段|
|完整示例|[最小 C++ 查询](#minimal-demo)|[最小 JavaScript 查询](#minimal-demo)|

## 方案一：原生 ROS 2

客户端从 API 根目录执行 `colcon build --base-paths interfaces/weld_interfaces`，加载 `install/setup.bash` 后通过完整服务名调用，例如 `/at/robot/status`。ROS_DOMAIN_ID 使用部署方提供的值；跨主机时 ROS_LOCALHOST_ONLY 为 0，并允许 DDS 发现和数据通信。这里不使用 WebSocket URL，也不向服务名附加工控机 IP。

需要先等待服务或 Action server 可发现；Topic 订阅的 QoS 与发布方匹配。自己的程序直接使用 rclpy/rclcpp；创建步骤见[构建与运行](#build-run)，完整查询见[最小 Demo](#minimal-demo)。

多网卡或需要指定系统主机发现地址时，参照[构建与运行](#build-run)中的“跨主机实例”：使用随包 Fast DDS XML 配置本机通信 IP 和初始发现目标，再从本机运行 Python 查询。示例中用户电脑为 `192.168.1.252`、系统主机为 `192.168.1.101`、相机为 `192.168.1.20`，三者不能混用。

## 方案二：rosbridge / WebSocket

客户端使用部署方提供的地址，例如 `ws://设备地址:端口/路径`。常见端口为 9090，实际端口、路径、TLS 和访问方式由部署配置确定。`127.0.0.1` 只表示客户端所在计算机，远程接入需填写实际桥接地址；HTTPS 页面使用可受信任的 wss:// 地址。

桥接端需已加载与系统匹配的 weld_interfaces，并能访问目标 ROS 2 服务；已有部署不需要调用方重新构建或部署。WebSocket 客户端不需要安装 ROS 2、接口包或 SDK。建立 WebSocket 连接后再发送消息；连接成功不保证某个 Service 已存在。Action、压缩与分片等功能依赖桥接器的实际能力，集成时应确认其支持情况。

## 同一个查询的两种请求

原生 ROS 2 请求对象只有以下两个字段：

```json
{"id":"","data":"robot_status"}
```

rosbridge 在外层增加操作、关联 ID 和服务名。args 保持原始请求字段，`data` 此处是固定查询字符串：

```json
{"op":"call_service","id":"robot-status-1","service":"/at/robot/status","args":{"id":"","data":"robot_status"},"timeout":5}
```

返回消息的 `op` 为 `service_response`，`id` 对应当前请求，`service` 对应目标服务。`result` 是桥接调用结果；业务响应在 `values` 对象中，包含 `status`、`message` 和 `data`。检查 `result=true` 和 `values.status=200` 后，再解析 `values.data` 内的 JSON 字符串。示例不预填设备状态响应。

外层 id 只用于消息关联，args.id 是接口请求字段；二者不能混用。WebSocket 消息格式见 [rosbridge 官方协议](https://github.com/RobotWebTools/rosbridge_suite/blob/ros2/ROSBRIDGE_PROTOCOL.md)。

## Topic 订阅与释放

例如订阅系统运行状态：

```json
{"op":"subscribe","id":"system-status-1","topic":"/at/system/status","type":"std_msgs/msg/String","throttle_rate":200,"queue_length":1}
```

收到 `op=publish` 的消息后读取 msg 对象；这个 Topic 的 `msg.data` 还需要 JSON 解析。结束时释放同一订阅：

```json
{"op":"unsubscribe","id":"system-status-1","topic":"/at/system/status"}
```

实时状态可以按刷新需求限频；APP点云文件下载使用独立[HTTP接口](point-cloud-download.md)，不是这里的Topic订阅。

## 超时与业务状态

两种方案都应设置发现、连接和响应等待时限。超时或断线后，服务端是否已经执行可能未知；不要自动重发控制操作。Service 业务成功也不等于动作完成，Action 应分别检查接受、反馈和最终业务结果；具体规则见对应接口。
