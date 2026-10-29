# 公共数据结构与分域状态码

同一个数字在接口结果、设备状态、任务反馈和 ROS Action 中可能含义不同。解析时先确定字段所属分域。未提供统一设备单位或枚举的字段只保留适用限制，不扩展取值。

<a id="code-service"></a>
## 接口结果码

|位置|值|含义|调用方处理|
|---|---|---|---|
|多数Service response.status|200|服务端该处理分支成功|继续解析result/data；不能据此判断动作完成|
|多数Service response.status|400|参数、状态、设备或业务拒绝|保留message和返回数据，不自动重试控制|
|多数Service response.status|500|处理异常|保留原始原因；实际设备状态可能未知|
|robot/get_pos response.status|0或200|当前正常路径可能保留默认0|仍要求cur_pos/joint_pos/flan_pos各六个有限数；不能套用其他接口|
|相机配置/控制 response.message.status|200/400/500/503|内层JSON的成功/输入错误/驱动失败/驱动不可用|先JSON解析，再取整数status，ROS返回没有顶层status|

这些不是HTTP状态。业务失败与通信失败分开：Python的RequestRejected/ServerError保留`raw`；C++typed调用保留原始响应，例程检查status并打印message/data/result；发现服务失败或超时则抛通信异常。超时只表示未得到响应，不证明操作没有执行。

<a id="code-action"></a>
## ROS Action终态

|值|ROS名称|处理|
|---|---|---|
|0|UNKNOWN|没有可靠结果|
|1|ACCEPTED|Goal已接纳，尚未执行完成|
|2|EXECUTING|执行中|
|3|CANCELING|取消处理中，不等于停止|
|4|SUCCEEDED|ROS成功终态；仍须业务结果成功|
|5|CANCELED|ROS已取消；Task后端cancel没有停止实现，不当成安全停止|
|6|ABORTED|执行失败；保留业务原因|

自动作业正常完成必须是ROS `4`且业务`project_status="101006"`；`101007`等待APP、`1011015`强制结束均不是正常完成。机器人运动Action的`Result.status`与任务Action的`status_message`不是同一结构。

<a id="code-device"></a>
## 焊机与机器人状态

|字段|数值/来源|实际含义|
|---|---|---|
|welder/set_enable.result|0/1|更新后的内部使能门控；关闭时0为正常；不直接写硬件使能寄存器|
|welder/welding.result|当前寄存器0位0缓存|下发后读取的位，不是同步请求回执，0和1均不能独立证明新动作完成|
|/at/welder/get_welder_status返回result，data=connect_status|0/1|内部连接状态不为2/为2；完整get_welder_data.connect_status保留内部数值2|
|key=certify_status|0/1|认证状态；查询要求已连接|
|key=ready_status、robot_ready_status|0/1|焊机准备/焊机侧机器人准备；不是机器人本体运动许可|
|key=enable_status|0/1|内部使能门控，不是新的设备反馈|
|key=weld_operate|0/1|当前停止/开始焊接状态|
|key=is_arcing|0/1|当前未引弧成功/引弧成功；响应status200本身不表示1|
|key=read_modbus|Modbus诊断返回值|诊断结果，未定义可通用推断的业务枚举|
|key=task_status|焊机状态机|与工程 101xxx、ROS Action 终态不同；未列出的数值按未知状态处理|
|robot/status.data.connect_status、power_status、subscribe_status|boolean|设备连接/上电/服务端采样状态，不是SDK连接状态|
|robot/status.data.motion_status|0/1|静止/运动；没有统一“已安全准备”位|

`set_synergic_mode.value`：0 分别调节、1 一元化；其他值不属于文档支持范围。面板 P19 需与目标设备配置一致。`set_welder_mode.value` 来自当前型号配置的 `mode_id` 列表，不能把某台焊机的 1/2/3 作为所有设备的固定枚举。

<a id="code-project-state"></a>
## 工程与工件反馈

`ATWeldTask`反馈、结果及task_feedback Topic中的JSON使用字符串状态码。project_time是状态更新的Unix epoch毫秒字符串，不是时间同步或事件序号保证。

|project_status|名称|处理|
|---|---|---|
|101001|Project_Analyzing|正在解析，等待反馈|
|101002|Project_Analysis|预规划完成；可查询规划数据，不是焊接完成|
|101003|Project_Run|运行中，不重复下发|
|101004|Project_Pause|业务暂停，不是机械停稳证明|
|101005|Project_Error|失败，保留原文|
|101006|Project_Finish|结合ROS4判定正常完成|
|101007|Project_Wait_App|等待显式开始，不是完成|
|1011008|Project_Json_Serialize_Error|解析/该分支错误；以msg查原因|
|1011009|Project_Param_Error|任务参数错误|
|1011010|Project_Workpiece_Param_Error|工件参数错误|
|1011011|Project_Tech_Not_Find|工艺查询失败|
|1011012|Project_Robot_Not_Start|机器人未启动|
|1011013|Project_Welder_Not_Start|焊机未启动|
|1011014|Project_Path_Planning_Error|规划失败|
|1011015|Project_App_Force_End|强制结束，不是正常完成|
|1011016|Project_IO_Force_End|IO强制结束枚举|
|1011017|Project_Error_Occupy|占用错误枚举|
|1011018|Project_Error_Excessive|调用过频|
|1011019|Project_Error_Teaching|示教相关错误|

服务内部APP_PROJECT_STATUS是0 EMPTY、1 RECEIVED、2 START_RUN、3 PAUSE、4 STOP_CANCEL、5 DONE、6 ERROR；并非上述反馈数值。控制允许状态在各控制接口页维护；不要给request新增一个task_status字段。

<a id="type-mcs-task"></a>
## MCS_WeldTask：工程 → 工件 → 焊缝 → 排道

顶层`project:object`和`workpieces:array`，整个对象序列化为`ATWeldTask.Goal.json_data:string`。数据库工程保存额外需要顶层`name`，它不是任务Action字段。详情中的数据库ID可能是string，任务对象中的ID为integer，不能原样反向写入。

|路径|类型|含义/赋值与单位|
|---|---|---|
|project.id/name/uid|integer/string/string|数据库工程ID、显示名称、任务核对UID；0仅是演示格式，不是现场引用|
|project.direct_run|integer|0等待显式开始，1按业务触发运行；例程使用0|
|project.loop_execution|integer|0单次/1循环；循环不是SDK自动重试|
|project.need_digital_start、digital_input_start|integer|是否需要IO触发0/1及输入通道编号（从0开始）|
|project.need_reservation|integer|是否使用预约策略0/1；策略对象reservation_config不由基础例程自动构造|
|project.system_config_id|integer|部署系统配置数据库ID，不是IP或任意默认0|
|project.execution_mode|MODE_TYPE integer|0 IDLE、1 MANUAL、2 AUTO（接口枚举），不能与direct_run混同|
|project.task_source|TASK_SOURCE integer|0 APP、1按钮盒；第三方示例沿用APP，不新增枚举|
|workpieces[].id/workpiece_id/workpiece_db_id|integer|工程工件行ID/工件引用/工件模板引用，字段不可互换|
|workpieces[].uid/name|strings|用于反馈关联的UID/工件名称|
|workpieces[].weld_process_id|integer|基础工艺数据库ID，不是工艺job_num|
|workpieces[].robot_tcp_id|integer|目标系统的TCP配置ID；其坐标及单位须与现场一致|
|workpieces[].laser_task_type|integer|实际枚举0 NOT_ACTIVE、1 SCANNING、2 POSITIONING；结构注释曾反写1/2，以枚举为准|
|workpieces[].scanning_welding|integer|0扫描后立即焊接；1不立即焊接，须同时满足普通模式、非循环且无其他焊接工件|
|workpieces[].scanning_mode|integer|0一键扫描；1定点扫描；本例3D路径用scanning_feature_points|
|workpieces[].tracker_type|integer|0线激光、1 3D相机、2无传感器|
|workpieces[].nodes[]|MCS_Node array|焊缝、扫描或安全点等节点；不是任意每道规划轨迹数组|
|nodes[].node_type|integer|0直线、1圆弧、2普通点、3安全点、4扫描、5规划节点（接口枚举）|
|nodes[].path[]|Point object array|x/y/z/w/p/r、uid、valid；当前SDK窄输入固定RobotBase/mm/XYZ Euler w,p,r/degree，其他驱动接口不能套此规则|
|nodes[].weld_process_id|integer|焊缝关联工艺ID；执行期间会从DB重新读取覆盖，不保证客户端快照|
|nodes[].is_multi/multi_layer_num/multi_pass_num|boolean/integer/integer|是否多道、总层数、总道数；与实际排道数组校验一致|
|nodes[].multi_pass_params[]|MCS_MultiPassParams array|每道偏移/方向及顺序，见下表|
|workpieces[].global_process|MCS_GlobalProcess object|共面检查、偏移和姿态规划设置；不能遗漏|

实际完整格式文件`examples/data/expected-task.json`，格式匹配不表示目标设备可直接执行。数据库读写字段差异见[字段契约](#field-data-contracts)。

<a id="type-multipass"></a>
## 排道与工艺对应

|字段|类型|含义/单位/范围|
|---|---|---|
|multi_index|integer|全局道顺序，从1开始；SDK要求输入连续，不替你排序|
|layer_index|integer|层号，从1开始；同一层允许多道|
|multi_offset_horizontal/vertical/start/end/x|numbers|水平/垂直/起点/终点/X偏移，接口定义为mm；不是机器人目标XYZ|
|multi_dir_horizontal|integer|0 RIGHT / 1 LEFT|
|multi_dir_vertical|integer|0 UP / 1 DOWN|
|multi_dir_forward|integer|0 FRONT / 1 BACK|
|multi_offset_dir_end、multi_offset_mode、weld_layer|integers|仅使用本文列出的取值；未列出的模式不属于 SDK 支持范围|
|global_process.coplanarity_check_mode|integer|0自由，不建立坐标且不走偏移；1共面；2非共面需要另一结构。SDK单直线多道仅支持1|
|global_process.enable_offset_correction/enable_free_pose/enable_input_safe_point|integers|偏移纠正/自由姿态/输入安全点开关，0/1；基础例程使用0，不扩展规划能力|
|global_process.target_accuracy_threshold|number|精度阈值；按规划模式使用，不能当真机精度认证|
|process_vec[].weld_bead_process_order|integer|关联每道工艺的全局顺序，应等于multi_index|
|process_vec[].layer_num|integer|应等于layer_index|
|process_vec[].bead_num|integer|层内序号，不是全局multi_index；层1道1、层2道1、层2道2对应1/1/1、2/2/1、3/2/2|

返回顺序不保证与请求关联顺序相同；SDK逐位置核对原始返回，不排序掩盖错配。执行期间仍会读取数据库配置；回读后修改配置可能影响执行，作业期间应冻结关联配置。

<a id="type-cloud"></a>
## 点云及坐标元数据

`ATPointCloud.points[]`为`ATPoint{x,y,z,w,p,r}`；并有`seam_point`及`timestamp:int64`。当前自定义消息没有frame_id/单位字段。VZ下载把RGB写入w/p/r，不能按欧拉角解析；timestamp可能为0，不使用焊机Topic的epoch规则代替。

Action反馈`sequence_id:uint32`从0开始，`total_blocks:uint32`为总块数；反馈到齐、序号不重复、不缺块且Result.status200/ROS4才可把NDJSON文件标为完整。大云是分块发送但服务端先持有完整云，客户端文件失败后仍是部分文件，不自动重试下载。

<a id="type-welder-config"></a>
## 焊机配置与反馈数据

`MCS_WelderConfig`中的ip、port、serial_number及模式列表在配置接口展开；每个range都是`{min:number,max:number}`。effective_input范围限制请求物理量，mapped_range负责寄存器映射，feedback_range负责反馈还原，三者不能混用。气保的A/V/弧长与激光的W/m/min按welding_process_type区分。

`get_welder_data.data`先解析JSON对象，再按字段读取；气保分支带current/voltage字段，激光分支带power/wire_feed_speed字段。Topic时间戳是发布时Unix毫秒，但Topic的real_time_wire_speed虽在IDL存在，当前publisher未赋值，0不是实测送丝停止证明。消息和设备设置字段不能共用“enable操作”描述。

## 工艺与库表读写

详情不是通用可写聚合：`process_detail` 缺少写入字段 `configParam`，配置详情的 `configPara` 也不是同一请求字段；工件详情的 `welds` 是数组，而写入需要 JSON 字符串；工程详情的 `project.id` 是字符串，而 update 需要整数。创建和更新必须使用对应写入模板，不能把详情响应作为 clone/update 请求。查询和关联工艺程序见模块示例。
