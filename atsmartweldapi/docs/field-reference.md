# 示例环境配置与数据创建

本页使用一组完整的**示例环境配置**说明设备接入、工艺创建和工程创建。下列地址、型号、配置 ID、工艺 ID 和工程 ID 不是协议默认值；部署到其他环境时必须替换为该环境的有效值。完整 Python/C++ 程序集中在“数据创建”模块。

## 设备与接入地址

| 对象 | 示例环境配置 | 使用说明 |
|---|---|---|
| 系统主机 | `192.168.1.101`，网卡 `enp3s0` | 这是 ROS 2、rosbridge 和点云下载服务所在主机，不是机器人或焊机地址。 |
| ROS 2 | Humble，domain 0 | 客户端加载匹配的 `weld_interfaces`，使用与服务端相同的 `ROS_DOMAIN_ID`，并确保 DDS 网络可达。 |
| rosbridge | `ws://192.168.1.101:9090` | `9090` 是 WebSocket 端口。外层 `result=true` 仅表示桥接调用完成，还要检查 `values.status` 并解析业务响应。 |
| 点云 HTTP | `http://192.168.1.101:10001/download/world.pcd` | HTTP 下载与 WebSocket、机器人端口和焊机端口互相独立；下载不会触发点云采集。 |
| 机器人 | 控制器 `192.168.1.8`；驱动 `Aubo`；子型号 `i7H`；服务端本机 IP `192.168.1.101`；scope `1000.0` | 示例配置行 ID 为 2，TCP 行 ID 为 1。初始化接口没有端口字段，不要把 `9090`、`502`、RPC 或 RTDE 端口填入该请求。 |
| 焊机 | 地址 `192.168.1.2:502`；配置型号 `MAG-500PROR PLUS` | 示例当前配置行 ID 为 2。调用配置或连接接口前，先通过 `welder_config_current_detail` 和 `welder_protocol` 选择与目标设备一致的型号、量程、模式和地址。 |
| 3D 相机 | 未配置 | 示例环境的 `camera3d_config_list` 返回空字符串，`camera3d_config_current_detail` 返回 `400 / Current config does not exist.`。可先使用设备搜索接口取得 GUID；连接、采集或扫描作业还需要有效的设备配置、手眼标定和 TCP。线激光地址不能作为 3D 相机地址使用。 |

机器人初始化请求示例：

```json
{"robot_type":"Aubo","robot_subtype":"i7H","robot_ip":"192.168.1.8","local_ip":"192.168.1.101","robot_scope":1000.0}
```

该请求对应 `/at/robot/init_robot`、`weld_interfaces/srv/ATRobotInit`。初始化后，机器人连接接口为 `/at/robot/connect`、`weld_interfaces/srv/ATBool`，请求 `{"enable":true}`。焊机连接接口为 `/at/welder/connect`、`weld_interfaces/srv/ATConnect`，示例请求 `{"weld_ip":"192.168.1.2:502","on":true}`。这些接口会操作设备，必须在配置、互锁和现场安全条件满足后显式调用。

完整参数及响应结构：[数据创建模板](../examples/data/field-create-templates.json)。其中 `reference_environment` 是说明元数据，不能作为 ROS 请求整体发送。

## 示例业务数据与创建结果

示例环境包含普通工艺 68、多层工艺 99 和工程 26；工艺 99 包含 6 层 12 道。工程的 `workpieces[]` 和 `nodes[]` 独立于工件模板库，因此工件模板列表为空不表示工程没有工件。工艺分组的 `id` 是数据库行 ID，`class_job_num` 是业务号，两者不能混用。

示例专用前缀：`APIDOC_VERIFY_20261015_114005_4c29660b`。

| 操作 | 示例名称/返回 ID | 依赖和结果判断 |
|---|---|---|
| 新建工艺分组 | `_group`，`data={"id":"28"}` | 服务`/at/data/process_class_add`，类型`weld_interfaces/srv/ATStringGeneric`；请求内层为name/description，主键由服务端分配。 |
| 新建普通工艺 | `_ordinary`，`data={"id":"114"}` | `/at/data/process_add`；`class_id="28"`、job_num=1、is_multi=0、1条焊道。 |
| 新建多层多道工艺 | `_multipass`，`data={"id":"115"}` | 同一process_add；`class_id="28"`、job_num=2、is_multi=1、6层12道；各道具体焊接参数在process_vec。 |
| 新建工程 | `_project`，`data={"project_id":27,"workpieceIds":[54,55]}` | `/at/data/workpiece_task_add`，同 ATStringGeneric；两个工件分别绑定工艺 114 和 115。 |
| 当前任务查询 | `data="null"` | 表示当前任务缓存为空，不是设备安全许可。数据创建流程不下发 Action，也不启动任务。 |

每个新增接口均先检查`status==200`，再解析外层`data`字符串。分组/工艺的`data.id`为十进制**字符串**；工程`project_id`和`workpieceIds[]`为**整数**。`workpieceIds[i]`对应输入`workpieces[i]`，不要排序，也不要替换运行UID。

**工程响应 `status=200` 后仍需回读详情。** 调用 `/at/data/workpiece_task_detail`，核对工程 ID、名称、工件 ID 顺序、UID 和工艺引用；回读失败或超时时停止流程，不自动重试创建请求。

## 工艺读写转换与多层多道归属

- `process_detail` 返回的 `groove.type` 是字符串，而 `process_add` 请求要求**整数**。创建请求必须完成类型转换，不能直接重放详情响应。
- 创建请求的 `class_id` 必须是十进制字符串；`job_num` 必须在同一分组内唯一。
- 详情的焊道基础字段扁平；写入需组装`weldBeadInfo={name,description,extension}`。`arc_tracking_params`读取对象在写端叫`arcTrackingPara`。
- 删除复制数据中的旧`id`和`weld_bead_process_id`，只创建新子表；`layer_num`、`bead_num`、`weld_bead_process_order`从详情文本转换为整数。`bead_num`是**层内**序号，`weld_bead_process_order`是全局顺序。
- 配置查询返回 `configPara`，写入字段名为 `configParam`。示例关联使用 `robot_id=2`、`welder_id=2`、`robot_tcp_id=1`；创建工艺关联不会修改设备配置。值 0 不表示设备或标定有效。
- 工艺级`is_multi`、`multi_pass_params[]`定义多层配置；每道具体电流、模式、速度等在`process_vec[]`。工程焊缝节点也有`multi_pass_params[]`：非空覆盖工艺，空数组继承。不要新增不存在的project级“多层工艺”协议字段。
- 示例多层工艺的层内道数为 `1,1,2,2,3,3`，共 12 道；`multi_index=1..12` 对应全局焊道顺序，`layer_index` 对应层号，`weld_layer=-1` 表示未填写 IoT 层类别。偏移单位为 mm。非零摆动停留时间的单位未在对外协议中确定，不提供非零示例。
- 工程聚合外层必须包含 `name`、`project` 和非空 `workpieces`，不能直接发送界面树。节点通过 `weld_process_id` 关联工艺，`workpiece_db_id=-1` 表示不关联已有工件模板。单平面直线多道规划必须显式提供 `global_process.coplanarity_check_mode=1`；仅保存工程不表示轨迹已经通过规划或设备验收。
- `project.robot_tcp_id`：**扩展字段，当前版本未使用，可不填。** 实际 TCP ID 填写在工件的 `robot_tcp_id`。

## 终端 ROS 2 调用

先加载 Humble 及随包接口。以下函数从完整模板构造请求，避免省略嵌套必要字段；创建时按返回值逐步绑定。运行前更换 `RUN_ID`，不要重放示例名称或固定 ID。ROS 超时后先查询是否已创建，不自动再次提交。

```bash
A=/path/to/atweldsystem-api
source /opt/ros/humble/setup.bash
source "$A/install/setup.bash"
export FIELD_TEMPLATE="$A/examples/data/field-create-templates.json"
export RUN_ID="$(date +%Y%m%d_%H%M%S)_$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')"
wire_request() {
  FIELD_KIND="$1" python3 - <<'PY'
import importlib.util, json, os
from pathlib import Path
path = Path(os.environ['FIELD_TEMPLATE'])
spec = importlib.util.spec_from_file_location('field_create', path.parents[1] / 'python/field_create.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
s = m.load_template(path); k = os.environ['FIELD_KIND']
if k == 'group':
    p = m.prepare_payloads(s, os.environ['RUN_ID'])['group']
elif k in ('ordinary_process', 'multipass_process'):
    p = m.prepare_payloads(s, os.environ['RUN_ID'])[k]
    cid = int(os.environ['CLASS_ID']); assert cid > 0
    p['class_id'] = str(cid)
else:
    ids = tuple(int(os.environ[x]) for x in ('CLASS_ID','ORDINARY_ID','MULTIPASS_ID'))
    p = m.prepare_payloads(s, os.environ['RUN_ID'], ids)['project']
print(json.dumps({'id':'', 'data':json.dumps(p,ensure_ascii=False)},ensure_ascii=False))
PY
}
ros2 service call /at/data/process_class_add weld_interfaces/srv/ATStringGeneric "$(wire_request group)"
# 检查 status=200 并解析 data.id；输入刚返回的值：
read -r -p '新分组 data.id: ' CLASS_ID; export CLASS_ID
ros2 service call /at/data/process_add weld_interfaces/srv/ATStringGeneric "$(wire_request ordinary_process)"
read -r -p '新普通工艺 data.id: ' ORDINARY_ID; export ORDINARY_ID
ros2 service call /at/data/process_add weld_interfaces/srv/ATStringGeneric "$(wire_request multipass_process)"
read -r -p '新多层工艺 data.id: ' MULTIPASS_ID; export MULTIPASS_ID
ros2 service call /at/data/workpiece_task_add weld_interfaces/srv/ATStringGeneric "$(wire_request project)"
# 解析project_id/workpieceIds，必须再查询详情，核对名称、ID顺序和全部工艺引用：
read -r -p '新工程 project_id: ' PROJECT_ID
ros2 service call /at/data/workpiece_task_detail weld_interfaces/srv/ATStringGeneric "{id: '$PROJECT_ID', data: ''}"
```

上面人工录入步骤仅说明终端绑定方式；Python/C++模块会自动绑定并校验返回/回读，推荐优先使用它们。不要在请求失败后继续填入旧ID。

## Python/C++ SDK模块与构建

```bash
python3 "$A/examples/python/field_create.py" # 默认离线，输出完整参数
# 需要创建独立记录时显式执行；该程序不下发任务：
python3 "$A/examples/python/field_create.py" --create --run-id "$RUN_ID"
```

先按现有[构建说明](build-run.md)构建随包接口和SDK；[最小原生C++ Demo](../examples/cpp/ros2_demo/README.md)及两种接入方案保持独立。新模块可作为安装后消费者构建：

```cmake
cmake_minimum_required(VERSION 3.16)
project(field_create_example LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
find_package(ament_cmake REQUIRED)
find_package(aotai_sdk_cpp REQUIRED)
add_executable(field_create /path/to/atweldsystem-api/examples/cpp/field_create.cpp)
target_link_libraries(field_create PRIVATE aotai_sdk_cpp::aotai_sdk)
```

```bash
source /opt/ros/humble/setup.bash
source "$A/install/setup.bash"
cmake -S /path/to/consumer -B /tmp/field-create-build
cmake --build /tmp/field-create-build
/tmp/field-create-build/field_create --input "$FIELD_TEMPLATE" # 仅离线
# 显式 --create --run-id 新标识 才创建数据库记录；不提供 --submit 或 --start。
```

Python/C++ 模块只负责创建独立业务记录并回读，不调用设备连接、相机采集或任务 Action。模块构建方式不影响原生 ROS 2 或 rosbridge 的直接接入方案。

## 关闭立即启动与下发限制

准确接口是`/at/task/task_action`，类型`weld_interfaces/action/ATWeldTask`；Goal只有字符串`json_data`，JSON中准确关闭字段为 **`project.direct_run`，整数`0`**，不是`execution_mode`，也不依赖默认值。

`direct_run=0` 阻止任务直接进入正式执行分支，任务随后等待 APP，可能反馈 `project_status="101007"`；该状态不是焊接完成。Action 接收仍会清理任务日志和焊接数据、覆盖当前任务临时记录并占用任务资源。Action cancel 不能完整释放任务；`task_destroy` 会操作焊机使能并停止机器人。因此，下发前必须确认当前任务、日志处理、资源占用和停止策略均符合目标环境要求。

完整 [Goal 示例](../examples/data/field-task-not-submitted.json) 使用当前任务结构的 `laser_tracking_params`，不包含兼容界面的 `track_mode`、`scan_mode`、选道或坐标扩展键。以下命令只在本地构造 Goal，不连接服务：

```bash
python3 - <<'PY'
import json, os
from pathlib import Path
# 使用任务 Action 结构；不要直接重放工程库 JSON。
task=json.load(open(Path(os.environ['FIELD_TEMPLATE']).with_name('field-task-not-submitted.json')))
assert type(task['project']['direct_run']) is int and task['project']['direct_run']==0
print(json.dumps({'json_data':json.dumps(task,ensure_ascii=False)},ensure_ascii=False))
PY
# 仅说明命令形状；满足全部任务前置条件后再由业务程序显式调用：
# ros2 action send_goal /at/task/task_action weld_interfaces/action/ATWeldTask '<上方Goal JSON>'
```

示例创建结果中的分组 28、工艺 114/115 和工程 27 已完成详情回读。示例没有任务下发或执行结果；不得将这些创建响应解释为任务已受理或焊接完成。创建的记录不会自动删除。
