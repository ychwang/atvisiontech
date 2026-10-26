# 使用限制

* **区分通信协议**：ROS 2服务名不是REST地址；APP点云文件另走[HTTP下载](point-cloud-download.md)，不能通过rosbridge调用该URL，也不能按ROS消息解析PCD附件。
* **控制安全**：运动、起弧、自动作业、相机采集和数据库写入必须在目标环境完成权限、互锁、设备状态和业务参数检查。接口返回成功不替代物理设备状态确认。
* **受理不等于完成**：ROS Service response、Action goal accepted、数据库 task 保存分别只说明响应/接受/存储；不能证明物理执行已开始或结束。
* **任务控制**：`task_services.data` 使用 `{"service_name":...}`；`task_start` 只接受 RECEIVED，`task_pause` 只接受 START_RUN/PAUSE，`task_continue` 只接受 PAUSE（服务端延迟 500 ms），`task_destroy` 接受 RECEIVED/START_RUN/PAUSE 并置 STOP_CANCEL。系统初始化期间控制请求会被拒绝。`task_destroy` 异步禁用焊机，Service 200 不表示设备已停机。`ATWeldTask` Action cancel 只接受取消请求，不执行完整任务停止，不能代替 `task_destroy` 或硬件急停。
* **点云**：`frame_id`、时间戳及点的 RGB/坐标编码以目标部署的消息和驱动为准；不得使用网页显示变换或通用 PCD 假设替代。
* **多层多道**：服务端不保证 `process_vec` 的回读顺序。客户端不得自行排序后假定服务端执行顺序一致；必须逐位置核对 `weld_bead_process_order`、层号、道号和 `multi_pass_params`。本接口不支持任意第三方轨迹直接下发。
* **工程存储与任务下发**：两者使用不同对象结构，planning_mode/touch_sensing_config在保存/回读时可能不保留；参见多层多道字段说明。
* **并发/断联**：写服务没有幂等键或跨服务事务。超时后先查询再决定人工/业务级补偿，绝不盲目重放运动、焊接或创建。

### 告警提示不是设备安全状态

`/at/system/get_system_alarm_status` 与普通 `/at/system/status` 不同：前者是 `alarm_code,timestamp_ms,` 成对文本，不是JSON；缓存非空时约1Hz重复发送，空集合不发布。当前 `alarm_reset` 会从提示缓存删除所有请求码，包括 `reset_ok=false` 的项。必须分别判断每项复位结果与真实设备状态，不能把提示消失、未收到Topic或整体status=200当作设备故障解除。

### 六模块接入验收边界

|模块|字段与判定重点|不能据此推断的结果|
|---|---|---|
|机器人|专用 `Client.robot_pose()` 接受该查询的业务status=0或200，并校验三组六元素；普通service默认检查200|查询/上电成功不证明运动完成；部分xCore部署tcp_v始终为0，需结合实际位姿与现场观测|
|焊机|先查询当前协议/配置，核对连接和授权；再按各控制接口检查status/result|配置存在不代表焊机连接；未连接时状态查询可能返回400，不能按0解释为已安全熄弧|
|3D相机|GUID来自发现；`config_str`/`control_str`均为JSON字符串；解析响应message中的内层status|连接成功不证明扫描成功；当前VZ驱动未连接时连connect_status查询也可能返回500|
|点云下载|HTTP GET `/download/world.pcd`；要求200、PCD解析成功及业务对应关系|404无可用文件；200不证明文件最新、坐标正确或属于当前工件|
|工艺与工程|完整写入、关联实际ID并回读；工程可以由API创建和编辑|模板引用的设备/TCP/路径不是生产默认；数据库成功不等于设备参数已应用|
|自动作业|完整`json_data`、匹配部署字段、反馈与业务终态；服务控制检查状态前置条件|direct_run=0仍可清理任务日志/焊接数据并占用资源，不是无副作用预检；状态`{}`不能证明安全可启动|

网页中空字符串有时表示未使用的字段，而非遗漏；缺少真实采样、报警码或轨迹的模板明确标注“不可直接提交”。相机配置中的采样列表、标定参数、摆动角度及任务工件扩展字段仍须按当前部署版本核对。`task_start_workpiece` / `task_workpieces_update` 在所审实现中为占位分支，不能用默认返回值证明功能已经实现。

随附手动焊接及相机采集示例是协议流程示范，不是具有硬件互锁和完整异常停机保证的生产控制器。异常后可能仍起弧或采集，不能依靠Python进程退出、Action取消或网络断开代替现场停止与状态确认。

- **物理完成复核**：已验证部署曾在运动故障、随后下电时返回 `SUCCEEDED + 101006`，但最终位姿未到目标。成功码不能代替故障历史、机器人静止和末端位姿验收；焊缝测试因奇异点暂停，不能据此声明完整三段运动或真实焊接已验证。见[自动作业执行流程](task-states.md)。
