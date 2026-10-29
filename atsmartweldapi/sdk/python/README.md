# AOTAI ROS 2 Python SDK

这是对现有 ROS 2 Service/Action/Topic 的轻量客户端封装，不是 HTTP/REST，也不会启动服务端或设备。导入模块和默认示例均离线；任何运动、任务或相机采集都必须由调用者显式执行。

## 安装

目标环境为 Ubuntu 22.04 和 ROS 2 Humble。API 交付目录已包含 `interfaces/weld_interfaces`；从 API 根目录构建接口包，再安装本 SDK：

```bash
source /opt/ros/humble/setup.bash
colcon build --base-paths interfaces/weld_interfaces --cmake-args -DBUILD_TESTING=OFF
source install/setup.bash
python3 -m pip install --no-deps -e sdk/python
# 若目标环境未采用 pip editable：
export PYTHONPATH="$PWD/sdk/python:$PYTHONPATH"
```

无第三方 Python 网络库依赖；`rclpy` 来自 ROS 2，`weld_interfaces` Python 类型由随包接口定义构建生成。

## 通用原生接口

```python
from aotai_sdk import Client
from weld_interfaces.srv import ATStringGeneric
with Client() as client:
    response = client.call(ATStringGeneric, "/at/...", {"id": "", "data": "..."})
```

`call` 同时接受消息实例或 dict（包括 rosidl 嵌套/数组字段）；`subscribe` 返回需显式 `release()` 的句柄；`send_action_goal` 返回 ActionHandle，调用 `wait_result(timeout=300)` 获取终态。服务错误保留在异常 `.raw`。通信/超时、4xx 请求拒绝、5xx 服务端失败、Action 终态失败彼此区分。非幂等写操作绝不自动重试。

## 已封装的实际端点

- `robot_status()`：`/at/robot/status`，默认 `data="robot_status"`；`robot_connect`、`robot_pose`、`robot_stop` 也为已封装 helper。
- `camera_search` / `camera_config` / `camera_control`：`/at/camera_node/search`、`/at/camera_node/config`、`/at/camera_node/control`；`camera_search` 可能触发设备发现，必须显式调用。
- `task_command(name)`：`/at/task/task_services`，wire 为 `id=""`、`data={"service_name":name}`；`task_destroy` 才是推荐停止命令，ROS Action cancel 不等于停机。
- `process_detail`：`/at/data/process_detail`；`submit_task`：`/at/task/task_action`。

焊机实时数据、参数设置，以及未列的机器人/数据库服务仍可通过通用 typed `call` 访问；必须根据交付站点的 endpoint manifest 选择准确 service 类型和 wire 字段，不应猜测端点。

## 生命周期与线程

`Client()` 创建私有 ROS Context、Node 与后台单线程 executor。同步公开方法必须从创建 Client 的线程调用，不能在回调中同步调用或 `close()`；后者会明确抛错。`close()` 仅释放通信，不 cancel/stop 机器人、焊机或任务。等待具有有限 timeout，其他线程 close 会唤醒等待方；超时只表示客户端未知服务端状态。

示例：`examples/python/basic.py` 默认离线；`multipass.py --execute` 有演示/确认/ID/工艺顺序闸门；`control.py` 是显式 start/pause/continue/stop/status/recover 命令；`subscribe.py --connect --topic robot` 只读等待一条消息（可选 `welder`、`task`、`camera-status`、`camera-points`，默认10秒；`--prefix` 仅用于隔离 mock）；`process_inspect.py --connect --source-id ID` 只读回显工艺详情和独立系统配置响应；默认离线。详情保留嵌套数据库 ID 且不含 `configParam`，不可直接写回新增/修改接口。

### 状态与异常边界

`call` 默认要求响应顶层 `status=200`；`robot_pose` 对 `get_pos` 正常响应使用 `(0,200)` 兼容，并要求三组数组各含 6 个有限值。`camera_config/control` 检查 `response.message` 内层 JSON 状态并保留原始 message；typed `call` 不会猜测任意字符串中的 JSON。`ServerError` 表示后端已返回 5xx，不是通信失败。


用户回调不得阻塞。订阅回调异常会记录为后续调用可见的通信/executor错误；Action反馈回调异常由wait_result报告。close等待当前回调返回，不强杀用户线程。Action句柄可`release()`释放本地资源而不停止任务；timeout后可继续显式等待或查询，不能自动重发。

## 直接设备映射（模块例程使用）

`Client` 还提供与 ROS 2 服务一一对应、不串联且不重试的直接方法：

- 焊机：`welder_config(id, data)`、`welder_connect(weld_ip, on)`、`welder_certify(data)`、`welder_robot_ready(enable)`、`welder_current(value)`、`welder_voltage(value)`、`welder_synergic_mode(value)`、`welder_enable(value)`、`welder_welding(enable)`、`welder_status(data)`、`welder_data()`。
- 机器人：`robot_init(robot_type, robot_subtype, robot_ip, local_ip, robot_scope)`、`robot_power(enable)`、`robot_subscribe()`、`robot_move_step(move_type, direction, speed)`，以及既有 `robot_connect/status/pose/stop`。

这些方法返回原始 ROS 响应；`status=200` 仅表示服务处理成功。焊接命令的 `result` 是当前缓存反馈位，关闭命令返回 0 可以是正常结果，不能作为统一成功码。起弧后查询 `welder_status("is_arcing")`，停止后查询 `welder_status("weld_operate")`。完整程序见 `examples/python/welder.py` 和 `examples/python/robot.py`；程序默认离线，随附的 200 A / 20 V 仅为隔离 mock 输入，不能作为生产焊接参数。

连接生产环境时，使用单独准备的输入，将 `demonstration_only` 设为 `false`、`site_confirmed` 设为 `true`，并显式传入 `--execute`。这些标志只解除示例程序的本地保护，不替代设备安全检查。相机 `search.enable` 原样发送，不会把字符串等错误类型隐式转成 `true`。完整入口见 `docs/module-examples.md`。

请求字典中的ROS bool字段必须是Python bool，字符串"false"或整数0/1会在发送前抛TypeError，不隐式转换成开启；本地参数错误不是通信或服务端拒绝。

## APP点云下载

APP 使用 [HTTP 点云文件下载](../../docs/point-cloud-download.md)，不使用 ROS 分块下载封装。SDK 中的点云 Action 方法仅供需要该协议的独立调用方使用，不属于 APP 推荐流程。
