工艺、工程和任务示例使用统一字段定义。调用前先阅读[工艺分组与工艺](process-workflow.md)、[工件分组](workpiece-group-workflow.md)、[接口依赖](interface-dependencies.md)和[示例环境](field-reference.md)。

`field_create.py/cpp` 使用示例环境的设备配置、分组 28、工艺 114/115 和工程 27 展示完整数据结构。程序默认离线；显式创建只新增独立记录并回读，不调用任务 Action。

# 按模块运行完整程序

完整源代码只在下方各模块维护一处，Python/C++标签选择整段可运行程序；接口页面链接过来，不再重复初始化或终端命令。示例数据仅用于理解格式，接入实际设备前需提供当前环境的有效输入。

## 运行约定

本节是可选 SDK 模块参考，不是接入系统的前置步骤。用户自建程序可直接使用 ROS 2 或 rosbridge，见[构建与运行](#build-run)。仅复用本节程序时，按 [Python SDK](../sdk/python/README.md) 或 [C++ SDK](../sdk/cpp/README.md) 准备依赖。在独立 API 目录中设置 `A=.`。普通示例默认离线；查询使用 `--connect`，可能操作设备的程序必须显式指定 `--execute`、`--download` 或控制子命令。随附设备输入仅允许连接隔离 mock；生产环境必须使用单独准备并确认的输入。

## 焊机控制

`examples/data/device-control.json` 的 `welder` 对象包含完整请求格式：`weld_ip`、`certificate`、电流 200 A、分别模式 0、电压 20 V、使能 1，以及当前配置结构要求的 power/wire 范围和 `welding_process_type=0`。这些数值仅用于隔离 mock，不是生产焊接参数。连接生产焊机前，先按[焊机查询、配置与连接顺序](welder-query-workflow.md)取得目标型号的量程和模式，并确认面板 P19 设置。

|步骤|调用与目的|进入下一步的判断|
|---|---|---|
|1|welder_config：先保存设备地址/量程/模式|status200及原始message；不是连接|
|2|welder_connect(ip,true)：等待连接、认证、安全恢复和缓存恢复|当前连接恢复确认status200/result1；断开分支响应result0（最终状态须回读）；超时不重试、不推断断开|
|3|welder_certify(serial)：核对序列号|status200/result1；当前connect也已自动认证|
|4|welder_robot_ready(true)：设置发给焊机的准备信号|status200；result为当前缓存位，不代表机器人本体就绪|
|5|welder_current(200)、welder_synergic_mode(0)、welder_voltage(20)|每次status200；模式0是分别调节，面板P19需现场配合|
|6|welder_enable(1)：打开服务端后续命令门控|status200/result1；不是此刻直接写硬件使能|
|7|welder_welding(true)，再welder_status("is_arcing")|起弧命令status200仅处理成功，查询result1才是当前弧状态确认|
|8|welder_welding(false)，再welder_status("weld_operate")|熄弧命令status200仍不证明停机，查询result0才是当前停止状态|
|9|welder_enable(0)、welder_robot_ready(false)|status200；关闭result0正常；不自动断开设备|

```bash
python3 "$A/examples/python/welder.py"  # 离线
"$A/.build/cpp/aotai_cpp_welder"          # 离线
# 下两条命令只连接已启动的隔离 mock；生产设备不得使用随附输入
python3 "$A/examples/python/welder.py" --execute --endpoint-prefix /api_device_mock --input "$A/examples/data/device-control.json"
"$A/.build/cpp/aotai_cpp_welder" --execute --endpoint-prefix /api_device_mock --input "$A/examples/data/device-control.json"
```

随附文件的 `demonstration_only:true` 只允许隔离 mock。生产环境必须另行提供完整输入，设置 `demonstration_only:false`、`site_confirmed:true` 并显式执行；这些标志不替代设备安全检查。程序打印每次 `status/result/message` 并核对状态；任一步错误、解析失败、状态不符或超时均返回非 0，不自动重试。异常后必须单独确认焊机弧状态和设备状态。

这是一条**独立手动控制**教学流程，不是“机器人运动时同时焊接”的自动作业程序。自动作业服务按工程/工艺负责运动、参数和起熄弧，不应与手动客户端并发控制。

## 机器人控制

同一文件的 `robot` 对象使用 Aubo、示例控制器和本机 IP、`scope=1000`，以及 `move_step` 的 `X/direction=1/speed=20`。`robot_subtype` 必填，示例值为 `i7`；SDK 原样发送，不补默认值。`direction` 是带符号的步进距离，不只是方向标志。执行前必须确认目标型号、位置和角度单位、TCP 及设备互锁。

流程：init_robot → connect(true) → power(true) → subscribe → status解析并检查连接/上电/采样 → pose检查三组六元素 → move_step → move_stop → status。上电成功仍可能带默认负载/TCP未应用警告，例程保留打印并停止后续运动（这是示例的保守规则，不把服务端200改成失败）；不要把三个布尔状态当安全许可。步进Service响应不是所有驱动到位保证，停止也不停止焊机。

```bash
python3 "$A/examples/python/robot.py"                  # 离线
"$A/.build/cpp/aotai_cpp_robot"                         # 离线
python3 "$A/examples/python/robot.py" --execute --endpoint-prefix /api_device_mock --input "$A/examples/data/device-control.json"
"$A/.build/cpp/aotai_cpp_robot" --execute --endpoint-prefix /api_device_mock --input "$A/examples/data/device-control.json"
```

`move_line` 和 `move_joint` 同时提供 Service 与 Action。此模块演示 `move_step` Service；运动 Action 另有位置反馈和 `waitArrival` 结果，当前 C++ SDK 未提供专用封装，可直接使用 `rclcpp_action` 和随附 Action 定义接入。

## 3D相机与点云

相机 Python 示例统一放在 `examples/python/camera/`。[68 个 config 命令目录](../examples/python/camera/README.md) 提供每条命令的独立脚本，读取示例无需参数；设置示例采用原值写回与回读核对，电机、激光等用例需先核对现场条件。完整扫描使用 [camera_scan_demo.py](../examples/python/camera/camera_scan_demo.py)，运行方式和结果格式见[扫描说明](../examples/python/camera/camera_scan_demo.md)。

3D 相机与线激光使用不同协议。先调用 search，从 `/at/camera_node/sensor_search_result` 的 `std_msgs/String.data` JSON 数组取得设备 GUID；连接配置文件至少包含 `command_type:"connect"` 和目标设备 `guid`，其他 VZ 配置字段按目标驱动填写。没有有效 GUID 时不要执行连接或采集。

```bash
python3 "$A/examples/python/camera/camera_capture.py"          # 离线
"$A/.build/cpp/aotai_cpp_camera_capture"                 # 离线
# 显式采集：CONFIG 是目标环境的 VZ 配置文件，不是随附演示数据
python3 "$A/examples/python/camera/camera_capture.py" --execute --config CONFIG.json --seconds 1
"$A/.build/cpp/aotai_cpp_camera_capture" --execute --config CONFIG.json --seconds 1
```

采集程序按connect → connect_status=1 → start_capture → 指定采集间隔 → stop_capture；开始成功不等于已有可下载点云。异常后采集是否仍在运行可能未知，不自动连接或重试。APP点云文件使用[HTTP下载](point-cloud-download.md)，取得`world.pcd`后解析显示；相机采集示例不自动下载文件，也不等同于扫描业务已完成。

## 工艺设置与关联

`process_inspect`读取实际工艺ID的详情及独立配置，检查两份JSON对象并保留原返回字符串；ID须来自process_list_query或目标部署，不使用示例0。

```bash
python3 "$A/examples/python/process_inspect.py" --connect --source-id "$PROCESS_ID"
"$A/.build/cpp/aotai_cpp_process_inspect" --connect --source-id "$PROCESS_ID"
```

此程序只查询：`process_detail` 不含写入字段 `configParam`，嵌套 ID 由数据库管理，不能直接回写到 `add/update`。完整创建请求使用 `field_create` 模块和 `field-create-templates.json`。多层多道输入的 `seams[].process_id` 转换为 `node.weld_process_id`，随后逐位置核对 `process_vec`。

## 工程管理

先列工程或工件库，再用返回的实际ID查询详情；`engineering`只读，不将详情原样回写：

```bash
python3 "$A/examples/python/engineering.py" --connect --kind project
"$A/.build/cpp/aotai_cpp_engineering" --connect --kind project
python3 "$A/examples/python/engineering.py" --connect --kind workpiece --id "$WORKPIECE_ID"
"$A/.build/cpp/aotai_cpp_engineering" --connect --kind workpiece --id "$WORKPIECE_ID"
```

成功后打印原始 JSON。`project` 包含 `workpieces`，工件包含 `nodes` 焊缝，节点包含基准 `path` 及排道/工艺引用；保存工程不表示任务已下发。完整任务对象见 `multipass` 程序和 `expected-task.json`。工程详情中的字符串 ID、工件查询的 `welds` 数组与写入时的 JSON 字符串必须按接口分别转换。

### 独立测试工程的编辑（仅数据库）

工程可以通过 API 新建、查询和编辑，不需要先在界面手工建工程。先用 `field_create.py` 新建带唯一 `APIDOC_VERIFY_` 名称的测试工程并回读，再使用[工程编辑示例](../examples/python/project_edit.py)：

```bash
# API 根目录；将 ID/旧名称/新名称替换为本次创建并回读的值。
python3 examples/python/project_edit.py --project-id "$PROJECT_ID" --expected-name "$OLD_NAME" --name "$NEW_NAME"
# 默认只显示离线计划；明确需要写测试工程时才增加 --write。
```

该程序仅允许 `APIDOC_VERIFY_` 测试工程：详情查询 → 核对 ID、名称及四个自动启动开关为整数0 → 完整更新 → 再次详情回读。它把 `task_name` 映射为写入顶层 `name`，把 `project.id` 从字符串转换为整数，同时保留全部工件 ID、节点、关联和扩展字段；不会提交 Task Action、启动任务或删除工程。不适用于工件库 `welds` 对象的更新。

更新不是 PATCH：不完整 `workpieces` 可能删除关联；因此不能只发送名称或一个工件。服务没有版本比较锁，请勿让其他客户端同时编辑这个工程。超时、返回 ID 不一致或回读不一致时停止，不自动重试、删除或回滚。数据库中的旧示例轨迹、TCP 或设备绑定仍不是获准执行的现场作业。

## 自动作业下发与控制

`multipass`组装任务、校验工艺回读、提交ATWeldTask、处理反馈及结果；共享演示输入默认只能离线。`control`是单独显式控制方，调用前核对当前project.uid，不自动暂停/继续/停止，也不自动重发任务。

```bash
python3 "$A/examples/python/multipass.py"               # 本地格式组装
"$A/.build/cpp/aotai_cpp_multipass" "$A/examples/data/multipass-input.json"
# 使用目标环境输入并完成安全检查后，才可由操作方显式指定 --execute
python3 "$A/examples/python/control.py" get_task_status # 只读
"$A/.build/cpp/aotai_cpp_control" status                 # 只读
```

任务direct_run0时下发仍会读取工艺并预规划，业务101007等待显式task_start；101003运行、101004暂停、ROS4+101006正常完成。task_pause/continue/destroy分别受当前状态约束；continue可能实际运动，task_destroy异步停止/禁用不等于急停。恢复先查询UID及状态，不自动重新下发。完整步骤见[多层多道](#multipass)的源程序及[码表](#code-project-state)。

## 多层多道

输入`examples/data/multipass-input.json`包含第三方提供的基准直线、层/道编号、每道偏移和工艺ID；双程序转换成相同expected-task.json。排道index是全局顺序，layer是层号，DB bead_num必须按层内累计。轨迹固定窄坐标契约、global_process共面mode1，没有任意每道轨迹直接导入能力。

显式执行前用真实系统配置/TCP/工艺引用替换0，确认坐标和单位，回读工艺并逐位置校验order/layer/bead；服务端运行期还会查DB覆盖工艺。SDK不排序掩盖DB无ORDER BY，不承诺快照或消除回读后修改竞态。详细字段由[排道数据类型](#type-multipass)维护；执行限制见[SDK契约](#sdk-contract)。
