# 构建与运行

接入系统**不需要构建或安装 SDK**。用户建立自己的程序，按接口定义直接通过原生 ROS 2 或 rosbridge 通信即可。以下命令以 API 交付目录为起点。

|接入方式|客户端需要准备|需要构建什么|
|---|---|---|
|原生 ROS 2 / C++|ROS 2 Humble、rclcpp、匹配的 weld_interfaces|接口包尚未安装时构建一次，再构建自己的程序|
|原生 ROS 2 / Python|ROS 2 Humble、rclpy、匹配的 weld_interfaces|接口包尚未安装时构建一次；Python 脚本无需 C++ 编译|
|rosbridge / WebSocket|可连接 WebSocket 的程序|无需安装 ROS 2、weld_interfaces 或 SDK；不需要构建任何 ROS 包|

## 方案一：原生 ROS 2

### 1. 准备接口类型

本交付随附 `interfaces/weld_interfaces`。若客户端已经安装与服务端匹配的接口包，加载其环境即可，不必重复构建；否则执行：

```bash
source /opt/ros/humble/setup.bash
colcon build --base-paths interfaces/weld_interfaces --cmake-args -DBUILD_TESTING=OFF
source install/setup.bash
```

API 根目录有 `COLCON_IGNORE`，从此目录构建时用 `--base-paths` 显式指定接口包。将当前目录记为后续示例的接口环境路径：

```bash
API_DIR="$(pwd)"
export ROS_DOMAIN_ID=0  # 示例环境
export ROS_LOCALHOST_ONLY=0
ros2 interface show weld_interfaces/srv/ATStringGeneric
ros2 service type /at/robot/status
```

客户端与服务端的 `ROS_DOMAIN_ID` 必须相同，跨主机需要 DDS 发现与数据通道可达。原生 ROS 2 使用服务名，不把工控机 IP 拼到服务名称中；接口定义必须与部署版本匹配。

### 2. 建立自己的 C++ 程序

以下在一个新工作区创建 `my_weld_client`，依赖只有 `rclcpp`、`weld_interfaces`，不依赖 `aotai_sdk_cpp`：

```bash
mkdir -p ~/weld_client_ws/src
cd ~/weld_client_ws/src
ros2 pkg create my_weld_client --build-type ament_cmake --dependencies rclcpp weld_interfaces --node-name robot_status_client
```

创建命令会生成 `package.xml`、`CMakeLists.txt` 和 `src/robot_status_client.cpp`，并配置可执行文件。把[最小调用 Demo](#minimal-demo)中的完整 C++ 查询程序放入该源文件，或从交付包复制作为起点：

```bash
cp "$API_DIR/examples/cpp/ros2_demo/src/main.cpp" my_weld_client/src/robot_status_client.cpp
cd ~/weld_client_ws
colcon build --packages-select my_weld_client
source install/setup.bash
ros2 run my_weld_client robot_status_client
```

最后一条命令会真实查询 `/at/robot/status`；先确认服务可用及查询条件。该程序不会下发初始化、连接、上电、运动或焊接命令。每次新开终端需先加载 `/opt/ros/humble/setup.bash`、接口包的 `install/setup.bash`、自己程序的 `install/setup.bash`，再设置相同通信环境。

在自己的业务代码中创建对应类型的 Service client、Topic subscription 或 Action client；按接口表填写请求，处理发现/响应超时，分别判断业务状态、Action 接受/结果及设备状态。不要将通信成功当成设备动作完成，也不要自动重发超时控制请求。

### 3. Python 程序

Python 同样直接使用 ROS 2：加载上述 ROS 与接口环境，通过 `rclpy` 创建节点，导入 `from weld_interfaces.srv import ATStringGeneric`，再调用 `/at/robot/status`。创建请求时设置 `id=""`、`data="robot_status"`；等待服务、发送异步请求并处理超时。响应 `status == 200` 后解析 `data` 中的 JSON，结束时销毁节点并关闭 rclpy。无需安装本交付的 Python SDK。

### 4. 只运行随包最小 C++ Demo

如果暂时不创建自己的包，可直接构建已经随附的原生程序：

```bash
cd "$API_DIR"
cmake -S examples/cpp/ros2_demo -B build/raw-demo -DBUILD_TESTING=OFF
cmake --build build/raw-demo -j2
./build/raw-demo/aotai_ros2_raw_query
```

默认只构建直接使用 `rclcpp` 的查询程序，不会构建 SDK。完整代码、超时和退出码见[最小调用 Demo](#minimal-demo)。

## 方案二：rosbridge / WebSocket

客户端无需安装 ROS 2、weld_interfaces 或 SDK。建立 WebSocket 连接，按[两种接入方案](#transport)发送 `call_service` 或 `subscribe` 等 JSON 消息即可。示例环境地址为 `ws://192.168.1.101:9090`；这是系统的 WebSocket 通信服务，不是机器人或焊机的地址。

运行 rosbridge 的主机需已加载匹配的接口类型，并能发现系统服务；已有服务端环境不需要由调用方重新构建、部署或重启。使用 HTTPS 页面的客户端应采用部署方提供的可用 `wss://` 地址。

从[最小调用 Demo](#minimal-demo)复制完整 JavaScript 到浏览器 Console，或用 Node.js 22+ 运行。将程序中的 `bridgeUrl` 改为实际桥接地址，再运行：

```bash
node --input-type=commonjs < examples/javascript/robot_status_rosbridge.js
```

先核对 `op/id/service`，再检查桥接 `result` 和 `values.status`；业务 JSON 字符串在 `values.data` 中。WebSocket 已连接不等于服务调用成功；超时或断线不自动重发。

## 可选模块参考

现有[模块示例](#examples)中的 Python/C++ 程序使用可选 SDK 封装，只在复用这些程序时才需要其依赖；它们不是用户自建客户端的前置步骤。直接接入系统无需安装或构建这些 SDK，也无需构建系统服务端。
