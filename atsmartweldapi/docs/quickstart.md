## 选择接入方式

用户建立自己的程序即可调用系统，**不需要构建或安装 SDK**：

- 原生 ROS 2：使用 `rclpy` 或 `rclcpp`，加载与服务端匹配的 `weld_interfaces`，直接创建 Service、Topic 或 Action 客户端。
- rosbridge：程序通过 WebSocket 发送 JSON；客户端不需要 ROS 2 或自定义接口包。

先阅读[两种接入方案](#transport)，按[构建与运行](#build-run)准备接口包并创建自己的程序；也可以从[最小调用 Demo](#minimal-demo)复制完整 C++ 或 JavaScript 查询程序。

客户端节点初始化或建立 WebSocket 连接只建立通信，不会替用户连接机器人或焊机设备。最小 Demo 查询 `/at/robot/status`，不发送初始化、设备连接、上电或运动命令。

## 阅读路径

[机器人](#robot)、[焊机](#welder)、[相机](#camera)、[工艺](#process)、[工程](#project)与[任务](#task)分别说明字段和返回值；[公共类型与状态码](#data-types)解释嵌套对象和枚举。

[模块示例](#examples)保留可选 SDK 程序供参考；只有复用这些程序时才需要对应 SDK，不影响直接使用系统 ROS 2 接口。

## 调用约定

- 原生 ROS 2：消息定义匹配、ROS domain 相同、DDS 网络可达；rosbridge：使用可达的 WebSocket 地址，桥接端已加载匹配消息包并能发现系统服务。
- 先等待服务可发现或桥接连接建立，再发送请求；按每个接口的规则检查业务状态和响应内容。
- Service 返回成功、Action 接受 Goal 和设备动作完成需要分别判断。运动、焊接及任务控制发生超时后先查询当前状态，不自动重发。
