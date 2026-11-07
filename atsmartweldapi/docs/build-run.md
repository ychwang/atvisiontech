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

### 3.1 跨主机实例：在自己的电脑查询 3D 相机配置

下面使用随包的可选 Python SDK 和 [camera_config.py](../examples/python/camera/camera_config.py)。Python 程序运行在用户电脑，通过原生 ROS 2/DDS 调用系统主机上的服务。所需文件均在 API 包内。

相机相关 Python 示例统一位于 `examples/python/camera/`。完整的 [68 个 config 命令用例](../examples/python/camera/README.md) 每条一个同名 `.py`，可从 `get_camera_config.py` 开始；完整采集使用 [camera_scan_demo.py](../examples/python/camera/camera_scan_demo.py)，详见[扫描运行说明](../examples/python/camera/camera_scan_demo.md)。

|配置项|本次实测环境|其他环境如何填写|
|---|---|---|
|用户电脑通信网卡 IP|192.168.1.252|填写本机真实绑定、用于访问系统主机的 IPv4 地址|
|系统主机 IP|192.168.1.101|运行 `/at/camera_node/config` 等 ROS 服务的计算机地址|
|相机设备 IP|192.168.1.20|由系统主机上的驱动访问；不要把它填成 DDS 发现目标|
|ROS_DOMAIN_ID|0|与服务端一致，0 只是本环境的值|

**先确认网络出口。** 在用户电脑执行：

```bash
ip -brief -4 address
ip route get 192.168.1.101
ping -c 2 192.168.1.101
```

本环境的正确路由包含 `dev ens38 src 192.168.1.252`。网卡名称不固定，以本机实际输出为准。多网卡、VPN 或代理环境要检查是否走了错误网卡或旧静态路由。虚拟机需要配置能双向访问设备网络的连接；本环境使用桥接网卡。ping 成功只证明 ICMP 可达，DDS 的发现和数据通信也必须双向可达。

**配置 DDS 使用的网卡和发现目标。** 随包提供 [examples/config/fastdds_client.xml](../examples/config/fastdds_client.xml)，适用于这里使用的 ROS 2 Humble / Fast DDS：

- `interfaceWhiteList/address`：改为用户电脑的通信网卡 IP，本例为 `192.168.1.252`。
- `initialPeersList/locator/udpv4/address`：改为系统主机 IP，本例为 `192.168.1.101`。

这个文件只配置客户端 DDS，不修改网卡地址或系统路由。它通过 UDP 使用指定网卡，并向系统主机发起发现；系统主机还必须能够向客户端通信。初始发现目标不是服务的独占绑定地址，同一 ROS domain 中应避免多个系统提供相同服务名。这里的 initial peer 也不是 Discovery Server，无需在 101 上另外启动发现服务器。

**首次使用先按上文构建接口包；以后每个新终端执行下面的命令。** 先进入解压后的 API 根目录（包含 `sdk`、`interfaces`、`examples`），再执行：

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONPATH="$PWD/sdk/python:${PYTHONPATH:-}"

export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
unset ROS_DISCOVERY_SERVER FASTDDS_DEFAULT_PROFILES_FILE
export FASTRTPS_DEFAULT_PROFILES_FILE="$PWD/examples/config/fastdds_client.xml"

python3 examples/python/camera/camera_config.py
```

若接口包已在其他工作区安装，将 `source install/setup.bash` 替换为该接口包实际的环境脚本路径。这里通过 `PYTHONPATH` 加载随包 SDK，不需要额外安装它。以上变量只影响当前终端及其启动的程序；修改 XML 或通信地址后，要重新启动 Python 客户端。

`camera_config.py` 会自动加载随包 `examples/config/fastdds_client.xml`，并设置 domain 0、Fast DDS 和跨主机通信；当前文件已经填写系统主机 `192.168.1.101`、本机网卡 `192.168.1.252`。在此环境中，加载 ROS、接口包和 `PYTHONPATH` 后即可直接运行，DDS 环境变量由脚本设置。换环境时修改 XML 中的 IP；domain 不为 0 时还需修改脚本中的 `ROS_DOMAIN_ID`。上面的完整环境命令仍适用于其他 Python/C++ 客户端。

示例固定发送 `{"command_type":"get_camera_config"}`，不需要命令行参数。查询部分的核心代码如下：

```python
import json
from aotai_sdk import Client

with Client() as client:
    request = {"command_type": "get_camera_config"}
    response = client.camera_config(json.dumps(request), timeout=15)
    print(json.dumps(json.loads(response.message), ensure_ascii=False, indent=2))
```

`Client` 查找的是服务名 `/at/camera_node/config`。IP 位于 DDS 配置文件里，因此 Python 业务代码无需填写系统主机 IP。

#### 在同一个 Python 程序中复用通信配置

保留随包 [camera_config.py](../examples/python/camera/camera_config.py) 作为完整示例。文件开头的环境配置必须在第一次创建 `Client()` 或初始化 `rclpy` 之前执行：

```python
import os
from pathlib import Path

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
```

|配置|作用|
|---|---|
|`ROS_DOMAIN_ID="0"`|使用 domain 0，需与服务端一致|
|`ROS_LOCALHOST_ONLY="0"`|允许跨主机 ROS 通信|
|`RMW_IMPLEMENTATION="rmw_fastrtps_cpp"`|选择本示例使用的 Fast DDS 中间件|
|`FASTRTPS_DEFAULT_PROFILES_FILE`|指定包内 XML，其中配置本机网卡 IP 和系统主机初始发现地址|
|移除 `ROS_DISCOVERY_SERVER`|清除继承的 Discovery Server 配置，使用本示例的发现方式|
|移除 `FASTDDS_DEFAULT_PROFILES_FILE`|避免另一配置文件变量与本示例的配置混用|

上述相对路径按脚本位于 `examples/python/camera/` 编写。移动脚本后需要调整 XML 路径；这段代码不会替用户安装或加载 ROS、`weld_interfaces` 和 Python SDK。

配置完成后，同一 Python 进程中的后续 `Client()` 都使用这套通信环境，可以调用相机、机器人、焊机等服务，不需要在每次请求前重复设置。例如在同一个客户端中连续查询：

```python
# 放在上面的环境配置之后；相机须已连接。
from aotai_sdk import Client

with Client() as client:
    print(client.camera_config('{"command_type":"get_camera_config"}', timeout=15).message)
    print(client.camera_config('{"command_type":"get_laser_config"}', timeout=15).message)
```

通信配置不代替设备连接、使能或任务前置条件。某个服务可调用，不代表所有设备都已就绪。SDK 的同步接口应在创建 `Client` 的线程中调用，不要在订阅回调里直接执行这些同步请求。

`os.environ` 只修改当前 Python 进程的环境，通常也会被它之后启动的子进程继承；不会修改父终端、其他已运行程序或系统配置。退出后从终端另行启动一个 `.py`，仍需在那个脚本开头设置，或先在终端统一 `export`。本示例把配置放在 `if __name__ == "__main__"` 中，因此仅 `import camera_config` 不会自动配置环境或发起查询。修改 DDS 配置后应重新启动客户端，不能认为给已经创建的 `Client` 修改环境变量会立即切换目标。

**查询前相机必须已经连接。** `camera_config.py` 只读取参数，不会自动连接。若收到 `Device not connected`，可先运行随包搜索示例：

```bash
python3 examples/python/camera/camera_search.py --search --seconds 30
```

然后将实际搜索结果中的 GUID 填入下面的单次连接请求；本例 GUID 属于上述实测设备：

```python
import json
from aotai_sdk import Client

with Client() as client:
    request = {
        "command_type": "connect",
        "guid": "a397a255-53be-41fc-996b-521413e9e22d",
    }
    print(client.camera_config(json.dumps(request), timeout=15).message)
    print(client.camera_config('{"command_type":"connect_status"}', timeout=15).message)
```

连接请求会改变设备连接状态；确认 `connect_status=1` 后再查询配置。连接请求超时时，结果可能未知，应单独查询 `connect_status`，不要直接重发连接。

2026-11-02 在上述网络环境已读到 `status=200`、`message="Camera configuration retrieved"`，`camera_config` 中包含曝光 `260`、模式 `fixed`、帧率 `203`、左右增益和 ROI。这些是本次实际读值，不是其他设备的默认值或推荐写入参数。

|现象|检查方法|
|---|---|
|找不到 `aotai_sdk`|确认位于 API 根目录并设置了上述 `PYTHONPATH`|
|找不到 `weld_interfaces`|确认已构建匹配接口包，并加载了它的环境脚本|
|`service unavailable`|检查服务端节点、domain、XML 中两处 IP、本机路由及双向 DDS 通信|
|ROS CLI 与 Python 发现结果不一致|确认两者终端环境相同；旧 `ros2 daemon` 可能沿用原环境，可停止 daemon 后重新检查|
|`Device not connected`|ROS 服务已有业务响应，但相机设备尚未连接|
|调用超时或没有输出|区分节点创建、服务发现和响应等待；服务 timeout 不覆盖整个节点初始化过程，不把超时当作设备执行失败或成功|

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
