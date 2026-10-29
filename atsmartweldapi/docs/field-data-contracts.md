# 工艺、工程与自动作业：字段契约

本页说明接口读取、写入或生成的字段。工艺读接口和写接口的结构并不互为逆变换；示例中的 `<…>` 必须替换为目标环境的有效配置或业务 ID，不能作为请求原值提交。

## 通用服务外层

`ATStringGeneric` 的服务请求是 `{id: string, data: string}`，响应是 `{status: int16, data: string, message: string}`。`data` 是**字符串**；若该接口有 JSON 结果，调用方先判断 `status == 200`，再 `JSON.parse(response.data)`。200 仅表示数据库服务已完成当前请求，不表示自动作业已经执行。

| 响应字段 | 解析方式 |
|---|---|
| `status` | 200：当前请求处理成功；400：输入或业务拒绝；500：服务异常。不同于设备或任务状态。 |
| `data` | 非空时是 JSON 文本；更新和伪删除成功时可为空字符串。 |
| `message` | 服务端原因文本；失败时必须保留，成功时可为空。 |

`ATQuery` 的请求是 `filters: KeyValue[]`、`page_number: uint32`、`items_per_page: uint32`、`sort_field: string`、`sort_descending: bool`；响应外层相同。工艺和工程列表 JSON 的 `total` 是匹配总数；工件组和工件列表使用 `data_size`。`data[]` 均可为空，不能使用统一字段解析所有列表。

<a id="type-process-write"></a>
<a id="fields-process"></a>

## 工艺聚合（`process_add` / `process_update`）

服务端把 `request.data` 解析为 JSON，并直接访问下列顶层字段；遗漏任一直接索引字段会抛异常或导致校验失败。`process_detail` 只用于读取，不构成可直接回写的对象。

普通工艺 114 和多层工艺 115 的完整请求见[示例环境配置与数据创建](field-reference.md)及 `field-create-templates.json`。该结构不是任意工艺的通用最小模板；不要将 `process_detail` 直接重放为写入对象。


| 路径 | 类型 | 服务端实际用途 / 填写限制 |
|---|---|---|
| `class_id` | string | 必须填写十进制字符串，并关联已有类别；默认工艺类别被拒绝。 |
| `job_num` | number 或数值文本 | 不可为 `null`；同一 `class_id` 内不能重复。 |
| `name` | string | 工艺名称。 |
| `groove` | object | 坡口参数对象。 |
| `multi_pass_params[]` | object array | 原样序列化到 `parameter_json`，数组长度写作 `weld_bead_number`。本页不提供空数组的创建用法。 |
| `configParam` | object | 写入配置—工艺关联。`process_detail` 没有这个同名写入对象；不能直接以 `process_config_detail` 的 `configPara` 替代。 |
| `global_process` | object | 写入全局工艺参数表；已登记的参数名可能触发参数字典校验。 |
| `process_vec[]` | object array | 每项写入一条焊道基础行、11 类参数行及关联。每项都必须有 `weld_bead_process_order`、`layer_num`、`bead_num` 和下方列出的嵌套对象。 |
| `process_vec[].welding_motion_params.weld_speed` / `safe_speed` | number | 校验范围 `(0, 1000]`。 |
| `process_vec[].welding_motion_params.weld_acc` / `safe_acc` | number | 校验范围 `(0, 4]`。 |
| `process_vec[].welding_motion_params.safe_distance` | number | 校验 `>= 10`；本接口不提供跨设备单位换算。 |
| `process_vec[].positioning_motion_params.positioning_speed` | number | 校验范围 `(0, 1000]`；本接口不提供跨设备单位换算。 |
| `process_vec[].weave_params` | object | `is_weave > 0` 时 weave_type 必须在 `SINE..CRESCENT` 枚举区间，且左右正弦振幅不能同时为 0；停留距离与停留时间不能两组同时非 0。 |
| `process_vec[].intermittent_params` | object | `is_intermittent > 0` 时只能有一条 `process_vec`；编号、长度和间隔还需满足下方规则。 |

`configParam`、`arcTrackingPara`、`weldBeadInfo` 的固定列和已解析成员在下方逐项列出。`extension` 的内嵌内容不由这些接口解析，不应承载调用方依赖的标准业务字段。查询详情不能无损转换为任意创建或更新请求，因此不能直接用于 `process_add/update`。

<a id="fields-engineering"></a>

## 工程聚合（`workpiece_task_add` / `workpiece_task_update`）

`request.data` 是**顶层工程库对象**，不是仅 `MCS_WeldTask`。外层 `name` 和 `project.name` 都会被读取：前者用于工程表名称及唯一性，后者作为 description。两者不一致时服务不会自动修正。

工程库保存需要顶层 `name`、`project`、非空 `workpieces`；其精确成员在下方“Action 的 project、workpieces[]、nodes[] 和点位”与“工程嵌套对象”中统一维护。


| 路径 | 类型 | 服务端实际用途 / 取值 |
|---|---|---|
| `name` | string | 必填、非 null；和未删除工程同名会被拒绝。 |
| `project` | object | 必填、非空；整个对象保存为工程 `task_detail`。 |
| `project.id` | integer（update） | update 时必填且必须存在。`project_detail` 返回的是字符串，调用 update 前必须转换并核对。add 不用它分配主键。 |
| `project.loop_execution` | integer | 接口定义：0 单次，1 循环。 |
| `project.need_digital_start` | integer | 接口定义：0 不需要，1 需要数字输入启动。 |
| `project.digital_input_start` | integer | 数字输入起始号；接口未声明允许范围。 |
| `project.direct_run` | integer | 0 不直接运行，1 直接运行。值 0 进入等待 APP；Action 接收仍会清理日志、覆盖当前任务缓存并占用任务资源。 |
| `project.need_reservation` | integer | 0 不预约，1 预约；配套 `reservation_config` 结构见下方对象成员表。预约策略仅使用部署方支持的值。 |
| `project.post_scan_welding` | integer | 扩展字段，当前版本未使用，可不填。不能作为阻焊开关。 |
| `project.need_confirm_after_scanning` / `need_confirm_after_planning` | integer | 扩展字段，当前版本未使用，可不填。不保证扫描或规划后等待。 |
| `workpieces[]` | object array | 必填、非空；数组下标写为数据库 `workpiece_order`，因此数组顺序就是工程内工件顺序。 |
| `workpieces[].id` | integer | update：`>=0` 更新该工程内工件记录，`<0` 新建；add 路径总是新建工程内工件。 |
| `workpieces[].name` | string | 必填可读字符串，保存到工件记录。 |
| `workpieces[].workpiece_db_id` | integer | `>=0` 时写模板关联；缺失或负数不写。 |
| `workpieces[].weld_process_id` | integer | 反序列化后加入工程—工艺关系集合。 |
| `workpieces[].nodes[].weld_process_id` | integer | 每条 node 的工艺 ID 也加入工程—工艺关系集合。 |

工程add/update的每个工件都必须包含`name`、`weld_process_id`和`nodes`；不要提交只含name的对象。

<a id="fields-task"></a>
<a id="type-task-action-detail"></a>
## Action 任务与反馈

`/at/task/task_action` 的 goal 只有 `json_data: string`。其内容是 `{project, workpieces}` 任务对象，不是数据库工程库外层 `{name,project,workpieces}` 的完整保存包装。提交时必须 `JSON.stringify`；ROS Action层先接纳Goal，业务占用、频繁提交和初始化状态在后续处理阶段校验。**Goal accepted 不代表任务已受理成功、更不代表执行完成。**

反馈、结果和 `/at/task/task_feedback` Topic 都把状态对象序列化为字符串：

```json
{
  "project_status": "101003",
  "project_time": "1730000000000",
  "workpiece_uid": "<可选>",
  "workpiece_status": "102008",
  "node_uid": 0,
  "workpieces": [
    {"uid": "<可选>", "workpiece_status": "102008"}
  ],
  "msg": "<失败路径可选原因>"
}
```

| 路径 | 类型 | 解析规则 |
|---|---|---|
| `project_status` | string | decimal 枚举文本，不是 int；`101006` 才是 Project_Finish。 |
| `project_time` | string | 服务端毫秒 Unix epoch 转为十进制文本。 |
| `workpiece_status` | string | 当前工件业务状态，不可替代工程完成状态。 |
| `workpiece_uid` | string | 部分阶段/错误路径出现。 |
| `node_uid` | string 或整数 0 | 未进入节点时可能序列化为整数 0，活动节点使用 UID 字符串。解析时检查类型，并兼容缺失或 `null`。 |
| `workpieces[]` | array | 部分路径提供逐工件状态；可能缺失。 |
| `msg` | string | 部分早期错误填入；可能缺失。 |

工程码：101001 分析中、101002 分析阶段、101003 运行、101004 暂停、101005 错误、101006 完成、101007 等待 App；1011008–1011019 是序列化、参数、工艺、设备、规划、强制结束和占用等错误码区间。工件码从 102001 开始，表示未开始、扫描、规划、焊接等阶段；完整映射见[任务状态](task-states.md)。

<a id="type-task-command-detail"></a>
## `task_services` 命令

请求 `data` 是 JSON 文本 `{"service_name":"..."}`。常用命令是：`get_task_status`、`task_start`、`task_pause`、`task_continue`、`task_destroy`；大小写/下划线均须精确匹配。未知名称返回 500。

| 命令 | 内部前置状态 | 200 的准确含义 |
|---|---|---|
| `get_task_status` | 无 | 返回缓存 feedback JSON；无任务反馈缓存时返回 `{}`，不是实时设备状态。 |
| `task_start` | 系统已初始化、APP 状态 RECEIVED(1) | 设为 START_RUN(2)，仅命令受理。 |
| `task_pause` | 系统已初始化、START_RUN(2) 或 PAUSE(3) | 设为 PAUSE(3)；重复 pause 也允许。 |
| `task_continue` | 系统已初始化、PAUSE(3) | 500 ms 后设为 START_RUN(2)，不是轨迹已恢复确认。 |
| `task_destroy` | RECEIVED(1)/START_RUN(2)/PAUSE(3)，EMPTY(0) 是特殊成功 | 设为 STOP_CANCEL(4)；初始化完成时另起线程关闭焊机 enable，不确认机器人停稳。 |

## 工艺写入对象成员

以下清单列出 JSON 可识别的**准确键名**。部分缺失键会使用成员初始值，但 `process_add/update` 仍会直接访问若干顶层和焊道对象，因此存在默认值不表示整个对象可以省略。标为“无显式初始化”的数值必须由调用方填写。

### `groove`、`multi_pass_params[]`、`global_process`

| 路径 | 类型 | 含义与填写方式 | 默认 / 限制 |
|---|---|---|---|
| `groove.type` | integer | 坡口类型。当前结构只序列化此字段；接口未提供通用业务枚举。 | 无显式初始化；写入时显式填写部署方支持的值。 |
| `multi_pass_params[].multi_index` | integer | 焊道序号（接口定义 1、2、3…）。 | 默认 0；排道结果应从 1 起连续性由调用方保证。 |
| `.multi_offset_horizontal` | number | NORMAL：相对前进方向右正左负；OVERALL_MOVE：焊缝沿 Y 位移。单位 mm。 | 默认 0。 |
| `.multi_offset_vertical` | number | NORMAL：Z+ 正/Z- 负；OVERALL_MOVE：焊缝沿 Z 位移。单位 mm。 | 默认 0。 |
| `.multi_offset_start` / `.multi_offset_end` | number | 起点 / 终点偏移补偿，单位 mm。 | 默认 0。 |
| `.multi_dir_horizontal` | integer | 水平方向：0 默认右/外角，非 0 为反向。 | 默认 0；推荐只使用 0/1。 |
| `.multi_dir_vertical` | integer | 垂直方向：0 默认 Z+，非 0 为反向。 | 默认 0；推荐只使用 0/1。 |
| `.multi_dir_forward` | integer | 运行方向：0 向前，非 0 向后。 | 默认 0；推荐只使用 0/1。 |
| `.multi_offset_dir_end` | integer | 终端偏移方向：0 默认向前，非 0 向后。 | 默认 0；推荐只使用 0/1。 |
| `.multi_offset_mode` | integer | 0=`NORMAL`（普通偏移）；1=`OVERALL_MOVE`（整体移动）。 | 默认 0。 |
| `.multi_offset_x` | number | OVERALL_MOVE 下焊缝沿 X 的位移，单位 mm。 | 默认 0。 |
| `.layer_index` | integer | 层序号（接口定义 1、2、3…）。 | 默认 0；执行顺序不由本查询排序。 |
| `.weld_layer` | integer | IoT 的打底/填充/盖面标志；`-1` 表示“未输入”。不要提交未列出的枚举值。 | 默认 -1。 |
| `global_process.coplanarity_check_mode` | integer | 0 自由（不建立工件坐标系，使用示教点位/姿态）；1 共面单坐标系；2 非共面组合焊缝多坐标系。 | 默认 0。 |
| `.enable_offset_correction` | integer | 是否启用纠偏；未在此结构定义数值枚举，按 0/非 0 之外行为不可保证。 | 无显式初始化；显式填。 |
| `.target_accuracy_threshold` | number | 到点精度阈值；结构未声明单位。 | 无显式初始化；显式填。 |
| `.smoothing_parameters` / `.planning_parameters` | string | 平滑 / 轨迹规划参数的原文字符串；这两个字符串的内嵌格式没有在该结构解析。 | 无显式初始化；填 `""` 只表示空文本，不等于安全规划参数。 |
| `.enable_free_pose` | integer | 0 未启用、1 启用；接口标记此项 2025-08-16 已废弃。 | 无显式初始化；新接入不要依赖。 |
| `.enable_input_safe_point` | integer | 0 不启用（按工艺生成安全点）；1 启用（用户手动输入安全点）；不设也没有安全点。 | 无显式初始化；显式填 0 或 1。 |

`process_multi_param_get` 的 `response.data` 是上述 `multi_pass_params` **数组本身**，例如：

```json
[
  {"multi_index":1,"multi_offset_horizontal":0.0,"multi_offset_vertical":0.0,
   "multi_offset_start":0.0,"multi_offset_end":0.0,"multi_dir_horizontal":0,
   "multi_dir_vertical":0,"multi_dir_forward":0,"multi_offset_dir_end":0,
   "multi_offset_mode":0,"multi_offset_x":0.0,"layer_index":1,"weld_layer":-1}
]
```

### `process_vec[]`：11 个写端直接读取的子对象

写入对象必须包含`arcTrackingPara`和`weldBeadInfo`。`arcTrackingPara`是写端键名，不能替换为读端的`arc_tracking_params`。

| 路径 | 实际子结构 / 精确成员 |
|---|---|
| `process_vec[].weldBeadInfo` | 写入焊道基础表。固定列见下方“数据库通用列与配置关联”；还需同级 `weld_bead_process_order`、`layer_num`、`bead_num`。不要从字段名称扩展未定义的业务键。 |
| `.welding_params` | `weld_mode`, `adjust_mode`, `weld_current` (A), `weld_voltage` (V), `weld_arclength`（允许范围 -5..5）, `weld_startarc_mode`, `weld_startarc_current`, `weld_startarc_voltage`, `weld_startarc_arclength`, `arcing_determination_time` (ms，默认100), `weld_startarc_time` (ms), `weld_startarc_transition_time` (ms), `weld_endarc_mode`, `weld_endarc_current`, `weld_endarc_voltage`, `weld_endarc_arclength`, `weld_endarc_time` (ms), `weld_endarc_transition_time` (ms), `weld_wire_feed_speed` (m/min), `weld_power` (W), `weld_startarc_wire_feed_speed` (m/min), `weld_startarc_power` (W), `weld_endarc_wire_feed_speed` (m/min), `weld_endarc_power` (W)。除明示字段外无安全默认值。 |
| `.weave_params` | `is_weave`（0 关闭，>0 启用摆焊）, `weave_type`（0 SINE、1 SPIRAL、2 TRIANGLE、3 TRAPEZOIDAL、4 CIRCULAR、5 SAWTOOTH、6 CRESCENT）, `weave_freq`, `sine_amplitude_left/right`, `left_stop_distance/right_stop_distance`, `left_stop_time/right_stop_time`, `direction_angle/elevation_angle`。启用时两侧振幅不得同时为 0，停留距离组与停留时间组不可同时非 0。停留时间和角度单位未形成跨驱动统一约定；目标驱动未明确提供单位时保持 0。 |
| `.blend_params` | `is_blend`, `blend_type`, `blend_speed_ratio`, `blend_voltage`, `blend_arclength`, `blend_current`, `blend_front_distance`, `blend_back_distance`, `blend_acc`, `blend_wire_feed_speed` (m/min), `blend_power` (W)。启用时 speed_ratio 和 back_distance 均不得为 0。`blend_type`：0 INSCRIBED_CIRCLE 内切圆，1 CIRCUMCIRCLE 外接圆。 |
| `.intermittent_params` | `is_intermittent`, `intermittent_weld_mode`, `intermittent_weld_length`, `intermittent_interval_length`, `intermittent_weld_number`, `intermittent_weld_form`, `intermittent_weld_end_form`, `is_raise_gun_in_interval`。启用时 `process_vec` 只能有 1 项；form=0 要求 number/length 非 0，form=1 要求 length/interval_length 非 0。`intermittent_weld_mode`：0 焊/间隔交替，1 固定焊段数并以间隔结束，2 固定焊段数并以焊段结束，3 固定间隔并以短焊段结束，4 固定间隔并以长焊段结束；`intermittent_weld_end_form`：0 WELD 焊段、1 GAP 间隔。设备允许范围另行确认。 |
| `.welding_motion_params` | `weld_speed`, `weld_acc`, `safe_speed`, `safe_acc`, `safe_distance`, `weld_working_angle`, `weld_forward_angle`, `weld_side`（0 自由、1 右、2 左）。显式校验：speed `(0,1000]`、acc `(0,4]`、safe_distance `>=10`；结构未给单位。 |
| `.positioning_motion_params` | `positioning_speed`, `positioning_distance`, `positioning_working_angle`, `positioning_forward_angle`, `positioning_joint_speed`。接口结构有 `positioning_side` 但宏**未序列化它**；不能发送后期望服务读取。speed 显式校验 `(0,1000]`。 |
| `.experiment_params` | `gas_supply_time`（秒）、`cooling_time`（秒）。 |
| `.laser_tracking_params` | `job_no`, `track_type`（保留字符串，如 150/250/250H 的注释举例，非枚举保证）, `process_id`, `weld_type`, `pcl_job_num`。入口仅校验 `process_id/job_no/weld_type >=0`。 |
| `.camera_tracking_params` | `job_id`, `job_num`, `job_name`。 |
| `.welding_torch_posture_params` | `weld_side`（0 自由、1 右、2 左）, `forward_angle`, `working_angle`, `rotation_angle`, `is_multi_attitude`（0 关、1 开）, `start_forward_angle`, `start_working_angle`, `start_rotation_angle`, `end_forward_angle`, `end_working_angle`, `end_rotation_angle`, `c_process_forward_angle`, `c_process_working_angle`, `c_process_rotation_angle`。角度单位未由结构声明。 |
| `.arcTrackingPara` | 写入 `at_weld_system_arc_tracking_param`。固定列见下方“数据库通用列与配置关联”；接口不解析 `extension` 的内嵌内容。 |

### Action 的 `project`、`workpieces[]`、`nodes[]` 和点位

下列为任务Action接受的顶层键。省略的字段可能采用默认值；默认值不表示规划参数、设备配置和运行条件已满足。

| 路径 | 类型 / 可操作取值 |
|---|---|
| `project.id` | integer；无显式初始化。 |
| `project.name` / `project.uid` | string；无显式初始化。 |
| `project.loop_execution` | integer：0 单次、1 循环。 |
| `project.need_digital_start`, `project.direct_run`, `project.need_reservation` | integer：接口定义均为 0 否、1 是。 |
| `project.digital_input_start` | integer，数字输入起始号从 0 开始。 |
| `project.system_config_id` | integer，系统配置 ID。 |
| `project.post_scan_welding` | integer；当前执行链未消费，不作阻焊开关。 |
| `project.need_confirm_after_scanning`, `project.need_confirm_after_planning` | integer；扩展字段，当前版本未使用，可不填。不保证扫描或规划后等待用户确认。 |
| `project.execution_mode` | enum integer：0 IDLE_MODE、1 MANUAL_MODE、2 AUTO_MODE；默认 1。**扩展字段，当前版本未使用，可不填。** 不能据此控制自动启动。 |
| `workpieces[].id` | integer；无显式初始化。 |
| `.workpiece_id` | integer，默认 1（数据库工件 ID）。 |
| `.uid`, `.name` | string。 |
| `.laser_task_type` | enum integer：0 不启用、1 扫描、2 寻位。 |
| `.scanning_welding` | integer：0扫描后立即焊接；1不立即焊接（普通planning_mode=0）。 |
| `.scanning_mode` | integer：0一键扫描、1定点扫描。 |
| `.nodes[]` | `MCS_Node` 数组；下表。 |
| `.weld_process_id` | integer，工件基础工艺 ID。 |
| `.global_process` | 上表 `MCS_GlobalProcess`。 |
| `.model_file_path_3d`, `.model_file_path_2d`, `.plate_material` | string；**扩展字段，当前版本未使用，可不填。** |
| `.workpiece_type` | enum integer：0 SELF_DEFINE自定义，1 RECT矩形，2 PIPE_GUARD管件护栏；默认0。 |
| `.workpiece_feature_parameters` | JSON object；矩形等模型的参数，字段随模型变，当前入口没有固定 schema。 |
| `.robot_tcp_id` | integer，机器人 TCP 配置 ID，需与工艺关联及实际工具一致。 |
| `.workpiece_db_id` | integer，工件库模板引用，不等于工程内工件 `id`。已有内嵌节点的非扫描自定义工件可使用 0；不要继承 -1，非扫描分支可能查询不存在的模板。见[自动作业流程](task-states.md)。 |
| `.is_crossing_welding`, `.is_auto_adjust_attitude` | boolean；默认 false。启用自动姿态调整时不要与空跑点组合使用。 |
| `.tracker_type` | enum integer：0 线激光、1 3D 相机、2 无传感器；默认 0。 |
| `.workpiece_coor`, `.coor_align_config` | 嵌套结构；Action会序列化该结构；本接口不提供通用的外部配置schema。 |
| `nodes[].uid`, `.name` | string。 |
| `.node_type` | enum integer：0 直线焊缝、1 圆、2 点、3 安全/空跑点（不焊）、4 扫描、5 规划。直线焊缝提供起终两点；不起弧的焊缝测试不能用 3 替代 0 来证明焊缝工艺已执行。 |
| `.path[]`, `.position_path[]` | Point 数组；寻位模式应使用 laser_task_type=2；旧结构注释写1并称position_path空可复制path，不能按过时注释选择模式。 |
| `.predecessor_node_uid` | string，前序节点 UID。 |
| `.groove`, `.weld_process_id`, `.welder_job` | 坡口对象、工艺 ID、焊机面板 job ID。 |
| `.is_multi` | boolean；false 关闭、true 启用多层多道。 |
| `.multi_layer_num`, `.multi_pass_num` | integer，手工输入层数/道数，默认均 1。 |
| `.multi_pass_params[]` | 上表 MCS_MultiPass；注释说明会覆盖数据库值。 |
| `.laser_tracking_params`, `.track_attitude`, `.welding_attitude` | 追踪参数；姿态对象含 working/forward/rotation angle、side（0/1/2）、distance、is_multi_attitude、multi_attitude_angel[3]。角度单位未由结构声明。 |
| `.waiting_time` | number，注释称安全点等待时间；无单位声明。 |
| `.dry_run_path_params` | `{node_uid,path,motion_type,speed,acc}`；Point path；motion_type 是 ROBOTMOVETYPE，0 MOVE_LINE直线、1 MOVE_CIRCLE圆、2 MOVE_JOINT关节、3 MOVE_PROCESS过程、4 MOVE_SPEEDLINE线速度、5 MOVE_PLANNING规划点；具体node能否使用该运动类型由执行路径决定。 |
| `.path_back_up[]` | Point 数组。 |
| `.is_enable_path_correction` | boolean，默认 false。 |
| `.reference_compensation` | number[][]，基准补偿；维度/坐标语义未在此定义。 |
| `.laser_enable` | integer，App 当前激光开关标志。 |

Point 的准确 JSON 键为 `x,y,z,w,p,r,uid,valid`。`x/y/z` 是位置，`w/p/r` 是姿态；本结构没有声明坐标系、位置单位和角度单位，故不能将 mm/deg 当成 API 不变量。`valid` 是 bool；Point默认构造数值均0，valid=false，uid=""；不能把缺失点位默认0当有效轨迹。

`extension` 不解析内嵌内容；`workpiece_feature_parameters`、预约、IoT、寻位和坐标系对象仅适用于部署方提供了对应模型或策略定义的场景。本交付不提供这些扩展对象的通用枚举或默认值。

### 工程嵌套对象

| 路径 | 精确成员与限制 |
|---|---|
| `project.reservation_config` | `{scheduler_strategy:string, scheduler_task:[{workpiece_name:string,digital_workpiece_start:integer}]}`；`digital_workpiece_start` 从 0 开始。`scheduler_strategy` 仅使用部署方提供的策略字符串。 |
| `project.iot_packet_params` | `{packet_id:string, packet_name:string}`。 |
| `workpieces[].workpiece_coor` | `{is_custom_coor:boolean, coor_creat_form:integer, coor_name:string, parent_coor_name:string, coor_points:Point[]}`。默认 `is_custom_coor=false`、`parent_coor_name="RobotBase"`；`coor_creat_form` 的数值0 THREE_POINT三点建系、1 SINGLE_POINT单点建系、2 CHOOSE选已有系；coor_points三点法按原点/+X/+Y顺序。 |
| `Point` | `{x:number,y:number,z:number,w:number,p:number,r:number,uid:string,valid:boolean}`。默认构造 x/y/z/w/p/r=0、valid=false；`uid` 默认空字符串。旋转组合是 `Rz(w)*Ry(p)*Rx(r)`；针对 Aubo 注释特别说明 w/p/r 对应其 rx/ry/rz 的映射，不能改写为任意四元数。坐标系、长度和角度单位未由该结构声明。 |

<a id="fields-db-columns"></a>

## 数据库通用列与配置关联（不是完整写入逆映射）

这些对象不是任意 JSON。数据库只保留已知列，未知键会被忽略；缺失成员不参与 INSERT/UPDATE，`configParam` 为空时不创建关联。显式 JSON `null` 会成为文本 `"null"`，不能用于清空字段。不要发送查询响应中的主键或依赖未说明的数据库默认值。

| 路径 | 类型与具体填写／解析方式 | 自动处理／限制 |
|---|---|---|
| `request.data.configParam.id` | integer：表记录主键；读取时使用，新增由数据库生成，不传回读id。 | 主键自动生成；不作为聚合写入请求字段。 |
| `request.data.configParam.name` | string：本行可读名称文本；空值不是工艺查找键。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.configParam.user_info_id` | integer：关联用户信息记录ID（不是用户名）。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.configParam.global_process_id` | integer：关联全局工艺记录ID；写端用服务生成的ID覆盖。 | 聚合写端覆盖用户值。 |
| `request.data.configParam.process_id` | integer：关联当前工艺ID；写端用示例工艺ID覆盖。 | 聚合写端覆盖用户值。 |
| `request.data.configParam.welder_id` | integer：关联焊机配置行ID，不是焊机连接IP。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.configParam.robot_id` | integer：关联机器人配置行ID，不是robot_type枚举。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.configParam.track_laser_id` | integer：关联线激光配置行ID。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.configParam.track_3d_id` | integer：关联3D相机配置行ID。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.configParam.robot_tcp_id` | integer：关联TCP标定行ID。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.configParam.hand_eye_calibration_id` | integer：关联手眼标定行ID。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.configParam.create_by` | string：创建人记录文本，服务未规定其值格式。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.configParam.create_time` | string：创建时间文本；本接口不定义日期格式或时区。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.configParam.update_by` | string：更新人记录文本，服务未规定其值格式。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.configParam.update_time` | string：更新时间文本；本接口不定义日期格式或时区。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.configParam.is_delete` | integer：软删除标志；聚合写端将这三类对象设为0。 | 数据库默认0；聚合写入时强制0。 |
| `request.data.configParam.description` | string：自由描述文本，不决定焊接行为。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.configParam.extension` | string：扩展文本；接口不解析内嵌 JSON。 | 可省略；不要依赖未定义的内嵌结构。 |
| `request.data.process_vec[].weldBeadInfo.id` | integer：表记录主键；读取时使用，新增由数据库生成，不传回读id。 | 主键自动生成；不作为聚合写入请求字段。 |
| `request.data.process_vec[].weldBeadInfo.name` | string：本行可读名称文本；空值不是工艺查找键。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.process_vec[].weldBeadInfo.create_by` | string：创建人记录文本，服务未规定其值格式。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.process_vec[].weldBeadInfo.create_time` | string：创建时间文本；本接口不定义日期格式或时区。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.process_vec[].weldBeadInfo.update_by` | string：更新人记录文本，服务未规定其值格式。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.process_vec[].weldBeadInfo.update_time` | string：更新时间文本；本接口不定义日期格式或时区。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.process_vec[].weldBeadInfo.is_delete` | integer：软删除标志；聚合写端将这三类对象设为0。 | 数据库默认0；聚合写入时强制0。 |
| `request.data.process_vec[].weldBeadInfo.description` | string：自由描述文本，不决定焊接行为。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.process_vec[].weldBeadInfo.extension` | string：扩展文本；接口不解析内嵌 JSON。 | 可省略；不要依赖未定义的内嵌结构。 |
| `request.data.process_vec[].arcTrackingPara.id` | integer：表记录主键；读取时使用，新增由数据库生成，不传回读id。 | 主键自动生成；不作为聚合写入请求字段。 |
| `request.data.process_vec[].arcTrackingPara.name` | string：本行可读名称文本；空值不是工艺查找键。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.process_vec[].arcTrackingPara.create_by` | string：创建人记录文本，服务未规定其值格式。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.process_vec[].arcTrackingPara.create_time` | string：创建时间文本；本接口不定义日期格式或时区。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.process_vec[].arcTrackingPara.update_by` | string：更新人记录文本，服务未规定其值格式。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.process_vec[].arcTrackingPara.update_time` | string：更新时间文本；本接口不定义日期格式或时区。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.process_vec[].arcTrackingPara.is_delete` | integer：软删除标志；聚合写端将这三类对象设为0。 | 数据库默认0；聚合写入时强制0。 |
| `request.data.process_vec[].arcTrackingPara.description` | string：自由描述文本，不决定焊接行为。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `request.data.process_vec[].arcTrackingPara.extension` | string：扩展文本；接口不解析内嵌 JSON。 | 可省略；不要依赖未定义的内嵌结构。 |
| `response.data.robotConfig.id` | integer：表记录主键；读取时使用，新增由数据库生成，不传回读id。 | 主键自动生成；不作为聚合写入请求字段。 |
| `response.data.robotConfig.name` | string：本行可读名称文本；空值不是工艺查找键。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `response.data.robotConfig.robot_type` | integer：正常typed JSON为整数：当前运行时枚举0 Aubo、1 xCore、2 Fuc、3 DUCO；随库robot_protocol仅有0/1条目，不证明2/3的部署配置/协议可用。与init_robot的字符串不同。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `response.data.robotConfig.robot_model` | string：型号文本，系统读取后赋到运行时robot_subtype；不要转换为robot_type。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `response.data.robotConfig.robot_ip` | string：机器人控制器IPv4文本，系统初始化时还会严格校验。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `response.data.robotConfig.robot_port` | string：端口TEXT，非整数；当前init_robot没有此字段。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `response.data.robotConfig.local_ip` | string：服务端通信网卡IPv4文本，不是第三方SDK主机。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `response.data.robotConfig.robot_scope` | number：工作范围实数，运行时作为位置前三分量边界，见机器人初始化页；数据库列不校验正值和有限值。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `response.data.robotConfig.library_path` | string：库路径文本；当前插件服务端按type选择固定驱动库路径，不因这列而加载任意路径。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `response.data.robotConfig.robot_comm_mode` | string：通信模式文本；具体取值由目标驱动配置提供。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `response.data.robotConfig.is_current_use` | integer：是否当前配置的数据库整数标志；系统配置读取选择本列=1的记录，不是已连接/上电。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `response.data.robotConfig.create_by` | string：创建人记录文本，服务未规定其值格式。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `response.data.robotConfig.create_time` | string：创建时间文本；本接口不定义日期格式或时区。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `response.data.robotConfig.update_by` | string：更新人记录文本，服务未规定其值格式。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `response.data.robotConfig.update_time` | string：更新时间文本；本接口不定义日期格式或时区。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `response.data.robotConfig.is_delete` | integer：软删除标志；聚合写端将这三类对象设为0。 | 数据库默认0；聚合写入时强制0。 |
| `response.data.robotConfig.description` | string：自由描述文本，不决定焊接行为。 | 数据库列允许缺省/NULL；这不代表业务请求字段可省略，不提供通用默认值。 |
| `response.data.robotConfig.extension` | string：扩展文本；接口不解析内嵌 JSON。 | 可为空；不要依赖未定义的内嵌结构。 |

`process_config_detail`的robotConfig中，整数和实数列通常返回数字，文本列返回字符串。部分部署可能返回全字符串，应兼容数值文本。数据库NULL在数字字段可返回0/0.0、文本字段可返回空串，不保证返回JSON null。先检查接口status，再容错解析，不能用0判断记录存在。

welderConfig仅指定字段二次解析：supported_welding_modes_protocols为数组，其余所有`*_range`为{min,max}对象，成员定义见[焊机配置字段](#welder_config)；其他TEXT不会自动按JSON解析。configPara是关联行，robotConfig是关联对象，名称相近不表示可以直接回写为configParam。

列表的 `total` 与 `data_size`、列表中的字符串 ID 与详情中的整数 ID、查询字段 `configPara` 与写入字段 `configParam` 均为不同概念，调用方必须按各接口结构分别解析。

`LASER_TASK_TYPE`：0 不启用、1 扫描、2 寻位。`task_start_workpiece` 和 `task_workpieces_update` 是占位接口，当前版本不执行对应业务操作。
