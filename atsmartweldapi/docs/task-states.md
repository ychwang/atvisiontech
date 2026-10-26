# 自动作业：受理、反馈、控制与恢复

可直接运行的 Python 入口：[`auto_task.py`](../examples/python/auto_task.py)，
操作步骤见[脚本使用说明](../examples/python/auto_task.md)。默认不连接设备，下发与启动分离。

从当前 TCP 生成三条焊缝：见[焊缝任务示例及验证边界](../examples/python/auto_job_motion.md)。该示例的通用 `--execute` 入口当前受限，不能把现场一次性验证脚本当作任意机器人均可直接执行的通用程序。

## 从工艺到焊缝执行的完整顺序

本节说明已有坐标的非扫描、单道直线焊缝任务；扫描任务另见[只扫描作业](scan-only-workflow.md)。

|阶段|接口与输入|必须核对的结果|
|---|---|---|
|1. 核对或创建工艺|工艺分组/工艺接口；再查 `process_detail` 和 `system_config_detail_by_process`|真实工艺 ID、类别、机器人和 TCP 关联一致；创建/更新使用对应请求结构，不能直接回写详情响应。|
|2. 构造工程|工程含工件，工件含焊缝 `nodes`；工件和焊缝填 `weld_process_id`，焊缝填 `process_class_id`|直线焊缝 `node_type=0`，`path` 为起点、终点；指定 TCP 与坐标系、长度和角度单位经过现场核对。|
|3. 保存与回读|需要持久化时调用 `workpiece_task_add`，回读 `workpiece_task_detail`|保存返回的工程 ID、工程内工件 ID，核对 UID、路径、工艺关联；写库不等于下发或开始运动。|
|4. 下发|`/at/task/task_action` 的 `ATWeldTask.Goal.json_data` 为完整 `project/workpieces` 的 JSON 字符串；显式 `project.direct_run=0`|保存 Action goal UUID 和工程 UID，监听反馈；不是只提交一个数据库工程 ID。下发会占用任务槽并可能清理日志/焊接数据。|
|5. 待启动检查|等待本 UID 的 `101007`，回读 `get_current_task`，查询 `get_workpiece_plan_path`|核对任务身份、实际规划、工艺、起点和设备状态；`101007` 只说明等待启动。|
|6. 启动一次|`/at/task/task_services`，`service_name=task_start`|外层 200 仅表示启动命令被接受；继续等待原 Action 和实际设备结果。|
|7. 验收与故障处理|持续记录 Action、任务反馈、报警及机器人状态/位姿|检查业务终态、执行期间故障以及实际最终目标；失败不自动重发或复位。|

各阶段都保存原请求和原响应。控制接口作用于**全局当前任务**，没有请求级 UID 锁；调用前回读 UID 只能降低误操作风险，不能替代独占控制。超时后先确认服务端是否已创建/接纳，不能换 UID 再提交一份。

## 焊缝节点、空跑点与禁焊是不同概念

|配置|含义|不能据此推断|
|---|---|---|
|`node_type=0`，`path=[起点,终点]`|直线焊缝，进入工艺、起收弧边界及焊缝执行流程|不保证实际起弧，也不保证轨迹可达。|
|`node_type=3`，单个目标点|安全/空跑节点，运动参数来自 `dry_run_path_params`|不能代替焊缝验证工艺速度、摆动、起收弧和焊缝切换。|
|`project.direct_run=0`|下发后等待外部启动|不是禁焊开关；不代表下发无副作用。|
|焊机使能、连接及现场独立禁焊措施|共同约束是否允许实际焊接|断开连接时的缓存 0 或状态查询失败，都不是完整物理禁焊证明。|

不起弧的焊缝测试仍使用焊缝节点，并独立核对禁焊条件。预规划 `is_arcing/is_arced` 是逻辑起收弧标记，不是实际弧反馈，不能为了通过空跑校验把这些标记删掉。也不要把焊缝换成空跑点后宣称焊缝流程已经验证。

### 工件 ID 与工件库模板 ID

- 工程创建返回的工程内工件 `id` 用于该工程实例，不等于工件库模板引用。
- 已有内嵌 `nodes` 的非扫描自定义工件，在已验证执行链中使用 `workpiece_db_id=0`，表示不引用工件库模板。
- 不要直接继承创建模板里的 `workpiece_db_id=-1`：当前实现仅在扫描分支跳过负 ID；非扫描分支可能查询不存在的模板并返回 `1011008 / Workpiece id does not exist.`。
- 这不是所有工件都填 0 的规则；需要工件库模板时应填写有效模板 ID，并验证所属模式。`1011008` 也可能对应其他解析失败，必须同时读取错误原文。

## 三个不同的结果

1. ROS Goal Response：`/at/task/task_action` 在ROS Action层先接纳Goal；后续业务校验发现任务占用、调用频繁或系统未初始化时可能返回 **ABORTED**。`accepted`绝不等于业务准备就绪。
2. 业务准备与执行：`ATWeldTask.Feedback.status_message` 内为 JSON；同一进度镜像在 `/at/task/task_feedback` 的 `std_msgs/String.data`。读取/解析/工艺加载/规划都会产生反馈，并可能失败。即使direct_run=0，下发也不是纯离线校验。
3. 终态：必须同时检查ROS终态和 `Result.status_message` 的JSON。**ROS SUCCEEDED + project_status="101006" 只是协议层完成条件，不是物理路径完成的充分条件**。强制结束也可能使用ROS SUCCEEDED，但业务码为1011015，不能算正常完成。

## 当前ProjectState（字符串形式出现在JSON）

|值|枚举/含义|客户端判断|
|---|---|---|
|101001|Project_Analyzing，解析中|等待反馈；不是可开始/成功保证|
|101002|Project_Analysis，分析/预规划完成|可查询预规划数据；仍非执行完成|
|101003|Project_Run|运行中，不自动重复下发|
|101004|Project_Pause|已进入业务暂停反馈；不是机械停稳证明|
|101005|Project_Error|失败，保留错误和原始结果|
|101006|Project_Finish|检查ROS终态，并复核故障记录、机器人静止及实际最终位姿|
|101007|Project_Wait_App|等待APP/外部显式开始，**不是完成**|
|1011008|Project_Json_Serialize_Error|解析或该代码分支映射的失败；不能仅据名称判定根因|
|1011009|Project_Param_Error|参数错误|
|1011010|Project_Workpiece_Param_Error|工件参数错误|
|1011011|Project_Tech_Not_Find|工艺查找失败|
|1011012|Project_Robot_Not_Start|机器人未启动|
|1011013|Project_Welder_Not_Start|焊机未启动|
|1011014|Project_Path_Planning_Error|规划失败|
|1011015|Project_App_Force_End|APP/服务强制结束，不是正常完成|
|1011016|Project_IO_Force_End|IO强制结束枚举|
|1011017|Project_Error_Occupy|占用错误枚举|
|1011018|Project_Error_Excessive|调用过频|
|1011019|Project_Error_Teaching|示教相关失败|

并非每个驱动或执行分支都会发布全部枚举值。未知状态码按失败处理并保留原文，不把任意非负值解释为成功。

## 反馈JSON字段与时间

`project_status`、`workpiece_status`使用字符串状态码；`project_time`是在状态更新处写入的Unix epoch毫秒字符串（不是硬实时事件序号）。实际执行分支还可能包含 `project_id,project_uid,workpiece_uid,node_uid,workpieces,task_source,weldingPassNum,retreat_distance`。这些字段不是每条错误/反馈都必有，早期受理失败可能只有project_status和msg。未知字段应保留，不因为缺少进度百分比而伪造进度。

```json
{"project_status":"101007","project_time":"0","project_uid":"demo-project-001","workpiece_status":"102001"}
```

该对象只说明字段格式，`time=0` 不是实际时间。工件状态与工程状态使用不同枚举，不能把工件焊接成功直接替代整个工程完成。

## 控制服务

共同ROS请求：`id=""`，`data`为`{"service_name":"task_pause"}`等JSON字符串。调用在全局当前工程上生效，没有request级目标UID绑定；例子在调用前回读project.uid，但仍非原子所有权锁。集成必须限制单一控制方。

|命令|允许状态与行为|重复与结果|
|---|---|---|
|get_task_status|返回当前反馈 JSON；任务线程不存在时返回 `{}`|可能没有状态或时间，不能据此推断空闲或停止|
|get_current_task|返回当前原始下发MCS JSON（project/workpieces）|用于核对project.uid；不是按UID查询既有任务|
|task_start|系统初始化完成且APP_PROJECT_RECEIVED → START_RUN|其他状态400，不自动重试|
|task_pause|系统初始化完成且START_RUN或PAUSE → PAUSE|允许重复PAUSE；Action仍挂起；响应不证明焊枪停稳|
|task_continue|系统初始化完成且PAUSE；延迟500ms后START_RUN|不允许任意状态继续|
|task_destroy|RECEIVED/START_RUN/PAUSE → STOP_CANCEL，异步尝试禁用焊机|EMPTY返回200/There is no task并可能异步禁用焊机；其他状态400|

任务控制状态0..6与101xxx反馈码不是同一套数值。停止需继续观察业务反馈、设备状态及现场互锁。**Task Action cancel返回ACCEPT但不执行任务停止**，不得用cancel或SDK close替代task_destroy，更不得替代硬件急停。

## 双语言完整执行步骤

1. 修改共享输入，提供真实坐标/TCP/系统配置/工艺ID，完成现场安全审核；移除demonstration_only保护只表示调用方确认，不是服务端安全认证。
2. `multipass.py --input REAL.json --execute` 或 `aotai_cpp_multipass REAL.json --execute`：回读每条焊缝的工艺，核对层/道数组位置，提交Action并保持结果等待。不得本地排序后声称后端相同。
3. 在另一个终端使用只读状态查询，核对project.uid和业务准备。Python `control.py get_task_status` / C++ `aotai_cpp_control status`。
4. 显式开始：Python `control.py task_start --expected-uid UID`；C++ `aotai_cpp_control start UID`。暂停/继续/停止分别用task_pause/task_continue/task_destroy或pause/continue/stop，不能定时自动连发。
5. 原Action进程消费反馈/结果。超时仅表示客户端未收到终态；查询实际状态，不重新下发。暂停本身不会完成Action。
6. 断联恢复：Python `control.py recover --expected-uid UID`；C++ `aotai_cpp_control recover UID`。只回读并比较UID；不匹配、未知、空JSON、旧时间或状态矛盾时停止自动控制，交由现场检查。当前API不能保证既有任务去重或从云块/动作断点恢复。

## 继续运行与回退距离不是同一个请求

APP 的回退距离输入框使用 0–20 mm、默认 5 mm；这是界面输入策略，**不是 `task_continue` JSON 的参数定义，也不是服务端范围校验**。
`task_continue` 只按任务状态继续；回退距离由独立服务配置：

|接口|消息类型|请求|成功判断|
|---|---|---|---|
|`/at/system/get_retreat_distance`|`weld_interfaces/srv/ATGetRetreatDistance`|空请求|`success == true`；读取 `retreat_distance` 与 `message`|
|`/at/system/set_retreat_distance`|`weld_interfaces/srv/ATSetRetreatDistance`|`retreat_distance:float64`，距离配置；不是默认示例|`success == true`；设置后不代表实际回退完成|

随附 SDK 没有专用回退便捷方法，应使用 typed call 并显式检查布尔 `success`。服务端不会应用 APP 的 0–20 mm 界面范围校验。实际回退还依赖焊接段、当前位置和轨迹规划；设置成功不表示机器人已经完成回退运动。

## 查询预规划轨迹（输出，不是排道输入格式）

当前任务服务还接受 `{"service_name":"get_workpiece_plan_path"}`，兼容名称 `get_workpiece_scan_path`。外层仍是 `ATStringGeneric`，`id=""`，`data` 为上述 JSON 字符串。成功200时 `response.data` 是当前任务 `workpieces` 数组；已有结果可能包含 `route_plan_result`、`motion_plan_result`。没有结果时不能伪造预览路径。

适用于 V1.0.12：收到 `Project_Analysis (101002)` 后可查询预规划轨迹；`101007` 表示等待开始，不是完成。路径按“工件 → 焊缝单元 → `pass_trajectory` → `path_attribute`”解析。查询输出不是任务 Goal，不能直接反向下发。

## 规划结果决定实际运动，不只看输入节点数

在已验证部署中，三条首尾相连、同工艺的直线焊缝可以规划为**一个连续焊缝组、一条焊道**，不是三个独立启停任务。一次规划包含：接近安全点 → 第一条起点 → 三条焊缝终点 → 末端退枪安全点。该六段结构是本次单道配置的观察，不能硬编码为所有任务的固定格式。

启动前逐项核对：

- 焊缝 UID、顺序、起终点和姿态是否与输入一致；`trajs_uid` 在接近/退枪等辅助段可能为空，不能把每段都当成独立焊缝。
- 实际 `motion_params.speed/acc`、交融、等待标记，以及工艺中的摆动/多道/间断焊选项。焊缝速度由工艺决定，不能用空跑点的 `dry_run_path_params` 代替。
- `safe_distance` 会引入接近/退枪偏移；当前直线实现按工具局部 Z 方向平移，不一定是世界 Z。最终验收目标应为**实际规划的最后一点**，可能不是最后一条焊缝的终点。
- 当前部署预览可能显示 `blend_radius=3`，执行时等待点会置为 0；中间交融点不保证逐点停稳。不能把预览半径直接等同于所有控制器指令，也不能把 `blend_params.is_blend` 与路径圆滑半径混为一谈。
- 预规划成功不是机器人运动学可达性、奇异点或碰撞认证；坐标系/TCP、完整路径及现场互锁仍需审核。

## 完成判定与异常恢复

实际验收至少同时检查：原 Action 正常结束、同工程 UID 的业务完成状态、设备无未处理故障且静止，以及末端位姿符合已审核最终目标。位置容差和姿态容差由应用明确配置，不是协议自带的通用值；末端到位本身也不证明每条焊缝质量合格。

已验证部署曾在运动故障、随后下电的情况下返回 `SUCCEEDED + 101006`，而最终位置未到达。客户端必须识别**状态与物理结果矛盾**并报告未通过；不能仅打印“作业完成”。保留暂停/故障历史，后来的完成码不能自动抹去该历史。

|现象|应对方式|
|---|---|
|`101004` 暂停，伴控制器 `-50102 / Singularity stop`|本次机器人报告奇异点，属于运行故障，不是凭此即可认定 API 格式错误。先处理姿态/关节构型和路径；不能原样自动继续。错误码含义按目标机器人型号核对。|
|起弧边界出现 `no need arc start`|表示该执行分支跳过实际起弧判定，不代表整个作业已经完成或焊接质量通过。|
|焊机未连接，查询使能/弧状态返回错误|保留状态不可读的事实；不要把错误强制改写为“禁焊已验证”。接口可能伴随焊机通信告警，不应直接归因为机器人奇异点。|
|任务提交/启动超时或客户端断线|结果可能未知；先核对现有任务 UID、状态和机器人实际状态，不重新创建、重新提交或反复启动。|
|`get_current_task` 返回 `{}` 或 `null`，而状态仍保留失败反馈|可能是任务清理后的空缓存，不代表旧任务未发生；结合持久化工程记录、反馈时间和实时设备状态核对。|
|准备阶段 `1011008` 且错误原文明确为工件模板不存在|先修正引用，再核对原失败任务、服务端空闲和机器人静止；不能把此恢复办法推广到运行中/暂停任务或其他错误。|

`task_start` 用于已接收任务，暂停恢复使用 `task_continue`。即使修正现场条件，也必须重新确认当前任务身份、报警和剩余规划；不要让重试器自动选择继续/销毁/重新下发。Action cancel、SDK close 和超时都不是机器人停止命令。

## 当前验证边界

已验证创建/回读、工艺与 TCP 关联、焊缝任务下发、等待外部启动、预规划查询及一次启动；实际运行因机器人奇异点暂停。**完整三段运动、真实起弧焊接及焊接质量尚未通过本次验证**。接口调用链可用与现场任务成功应分别记录，不能合并成“已全流程验证”。
