# AOTAI C++ SDK (ROS 2 Humble / C++17)

Native ROS 2 client wrapper; it is not HTTP/REST and does not start any server. Requires `rclcpp`, `rclcpp_action`, and the `interfaces/weld_interfaces` package included in this API distribution. The vendored `json.hpp` is nlohmann/json (MIT; see `THIRD_PARTY_NOTICES.md`).

```bash
source /opt/ros/humble/setup.bash
colcon build --base-paths interfaces/weld_interfaces sdk/cpp --cmake-args -DBUILD_TESTING=OFF
source install/setup.bash
```

`Client` owns an isolated ROS context, node, single-thread executor and executor thread. Do not synchronously call the client or destroy/close it in a subscription/action callback. `close()` only releases local ROS resources; it never stops a robot or task. Calls do not retry. A timeout means outcome unknown.

`cancel()` sends only ROS Action cancellation and is not `task_stop()`; use explicit `task_stop()` (`task_destroy`) then observe status/result. `submit_task()` acceptance only means ROS accepted its goal; it is not execution success.

## 示例与线程约定

- `aotai_cpp_basic`：无参数仅输出协议提示；`--connect` 才做只读状态查询。
- `aotai_cpp_multipass INPUT.json`：默认只转换和打印；`--execute` 要求 `coordinate_contract.confirmed=true` 并提供有效业务 ID，满足后才连接 ROS。
- `aotai_cpp_control <start|pause|continue|stop> <工程UID>`：每个控制命令均显式；先查询当前任务并核对 UID。断联恢复只应查询，**不得**自动重发任务。
- `aotai_cpp_subscribe --connect --topic robot`：只读等待一条消息（可选 `welder`、`task`、`camera-status`、`camera-points`，默认10秒）；`--prefix` 仅用于隔离 mock，收到或超时后显式释放订阅。
- `aotai_cpp_process_inspect --connect --source-id ID`：只读回显工艺详情与独立系统配置响应；默认离线。详情含数据库嵌套 ID 且不含 `configParam`，不能直接写回新增/修改接口。

一个 `Client` 创建独立 ROS context、node 和单线程 executor。同步调用及 `close()` 不可从 SDK callback 调用（会抛出 reentrant 错误）；用户 callback 不应阻塞。订阅返回句柄必须由调用方持有，销毁/释放后停止接收。Action 句柄同样必须在等待期间保活。`close()` 只释放本地通讯资源，不停止任何设备或任务。

## 安装后集成

通过 colcon 安装后加载 `install/setup.bash`；使用 `find_package(aotai_sdk_cpp CONFIG REQUIRED)` 并链接 `aotai_sdk_cpp::aotai_sdk`。若使用单独安装前缀，将该前缀加入 `CMAKE_PREFIX_PATH`。

`call<Service>()` 返回完整 ROS 响应，调用方必须检查端点 status/业务字段；`GenericReply.accepted()`仅表示服务status200。camera_config/control从message内层JSON提取status，同时保留完整原始message。`TaskResult.business_success`仅允许ROS SUCCEEDED和业务101006；强停1011015或畸形JSON不是成功。原始status_message与action_code保留。


控制工具还支持只读`status`、`current`与`recover <UID>`；recover仅核对当前工程UID并查询，不自动继续或下发。所有写控制要求UID匹配；回读不是原子所有权锁，系统应只允许一个作业控制方。

C++ Client必须在所有外部调用结束后由拥有方线程析构；不能在回调中删除自身或释放最后一个Client所有者。显式close可以由另一线程中断pending wait，但仍须join调用线程再析构。close等待当前非阻塞回调结束，不强杀用户代码。

## 直接设备映射（模块例程使用）

`Client` 提供与服务一一对应的 `welder_*`、`robot_*` 方法；它们不组合命令、不切换模式、不重试。`GenericReply` 保留 `status`、`result`、`message` 以及适用时的 `data`。`result` 是服务端原始缓存反馈或读值，不能统一按非零或零判断成功；先检查服务 `status`，再按业务查询 `is_arcing`、`weld_operate` 或 `robot_ready_status`。`aotai_cpp_welder`、`aotai_cpp_robot` 默认离线；随附输入仅用于 `--execute --endpoint-prefix /api_device_mock`。连接生产环境时使用单独准备的输入，设置 `demonstration_only:false`、`site_confirmed:true` 并显式传入 `--execute`；这些标志不替代设备安全检查。

`welder_current/voltage`直接返回`ATFloat::Response::SharedPtr`，保留double反馈，不转换为整数。其它新增便捷方法的GenericReply.result保持int64（原服务可能为int16/int64）；ATEmpty没有result，包装0无业务含义。welder_connect默认5秒、可显式timeout，其他便捷Service通常3秒；typed call可自选timeout。robot_status默认robot_status，任何显式data原样发送（旧{}隐藏替换已纠正）。

## APP点云下载

APP 使用 [HTTP 点云文件下载](../../docs/point-cloud-download.md)，不使用 ROS 分块下载封装。SDK 中的点云 Action 方法仅供需要该协议的独立调用方使用，不属于 APP 推荐流程。
