# SDK 双语言实施契约

## 传输与并发
Python rclpy；C++17 rclcpp/rclcpp_action + 当前weld_interfaces。连接即创建专有 Context/Node/单线程executor及后台线程，不启动服务端。每个client允许一个拥有生命周期的外部调用线程；回调在后台executor，禁止在回调内同步调用或close（检测并抛出明确错误）；严禁在回调线程析构client（生命周期违约会终止进程，不承诺抛出可恢复错误），回调不得长时阻塞。Action/Subscription句柄需保持client活着。close不stop/cancel设备，仅释放通信；等待操作须能被close唤醒，超时有限。业务封装不重试。

## 实际功能对等（业务覆盖，不要求同名便捷方法）

|业务能力|Python|C++17|后端边界|
|---|---|---|---|
|通用Service|`call(Type,name,request,timeout)`，返回原始ROS类型；非200按约定抛错|`call<Type>(name,shared_request,timeout)`，返回原始ROS类型，由调用方检查status|目录全部Service；不生成新端点|
|Topic|`subscribe(Type,name,callback)`、句柄`release()`|`subscribe<Type>(name,depth,callback)`、句柄`reset()`|目录全部Topic；释放不停止设备|
|机器人|`robot_connect/status/pose/stop`；运动用typed call|`robot_connect/status/stop`；位姿和运动用typed call|ATRobotMove是Service，不是Action；get_pos正常status可能0，须检查三个6元数组|
|焊机|typed call及subscribe|typed call及subscribe|连接ATConnect、参数ATFloat/ATInt、开关ATBool、实时Topic；无自动重试|
|相机|`camera_config/control`解析内层status；搜索用typed call|`camera_search/config/control`；status在内层JSON|LaserConfig.config_str、LaserControl.control_str；不能读取不存在的ROS response.status|
|工艺/工程|`process_detail`；其余CRUD typed call|`process_detail`；其余CRUD typed call|`process_detail`的ID在request.id，保存工程不是执行|
|任务控制|`task_command(service_name)`|`task_command`与task_start/pause/continue/stop便捷方法|task_services请求id空、data含service_name；stop映射task_destroy|
|任务下发/反馈/结果|`submit_task`、ActionHandle.accepted/wait_result/cancel|`submit_task`返回goal句柄、wait_result、cancel|仅正常业务101006+ROS SUCCEEDED为正常完成；cancel不是停止|
|本地排道转换|`assemble_task`、validate_execute_input、verify_process_order|Client::assemble_task、validate_executable|SDK 本地功能，不是服务端 API；两种语言使用相同输入、输出和拒绝规则|

Python `CommunicationError` 表示通信、超时或 close；`RequestRejected` 表示服务已返回 4xx 等拒绝，`ServerError` 表示服务已返回 5xx，`ExecutionFailed` 表示执行、反馈或结果格式失败，`.raw` 保留原始响应。C++ 使用 `ErrorKind` 表示本地通信和超时，typed 响应与 `GenericReply` 保留 `status/message`，`TaskResult` 保留 ROS result code 和原始 `status_message`。调用方必须分别检查 `accepted` 和 `business_success`，不能把业务失败当成网络失败，也不能把 accepted 当成正常完成。

Python通用send_action_goal是额外低层工具；C++基础版对任务Action提供业务封装，不承诺任意Action模板。

## 第三方排道输入与输出契约
两个SDK读取同一 examples/data/multipass-input.json，输出同一 expected-task.json。转换函数 assemble_task(input) 是SDK本地功能，不是服务端API。
输入需要 schema_version=1, demonstration_only=true, coordinate_contract={frame,position_unit,orientation_convention,angle_unit,confirmed}, project={uid,name,system_config_id}, workpiece={uid,name,robot_tcp_id,global_process}, seams=[{uid,name,process_id,base_path:[{x,y,z,w,p,r}],passes:[{index,layer,offset_horizontal_mm,offset_vertical_mm,offset_start_mm,offset_end_mm,direction_horizontal,direction_vertical,direction_forward,direction_end,weld_layer}]}]。`global_process` 精确包含 `coplanarity_check_mode,enable_offset_correction,target_accuracy_threshold,smoothing_parameters,planning_parameters,enable_free_pose,enable_input_safe_point`，并原样写入输出 `workpieces[0].global_process`。
默认演示 process_id=0、system_config_id=0、robot_tcp_id=0、coordinate_contract.confirmed=false，assemble允许、execute validation拒绝。此**窄 mapper**无任何坐标/姿态转换，且固定只接受 `frame=RobotBase`、`position_unit=mm`、`orientation_convention="XYZ Euler: w,p,r"`、`angle_unit=degree`；`confirmed=true` 不能覆盖其它格式。该限制不证明所有机器人 get_pos 都输出该格式（例如实际驱动可能用 rad），第三方必须先转换并现场确认。真实执行还要求字段完整/有限数值/非重复uid、正ID、confirmed=true、demonstration_only=false。
本例限制 `node_type=0`、`base_path` 恰好两个点、`passes.index` 按 1..N 连续且 `layer>=1`；同一焊缝各道按一个数据库工艺的 `process_vec` 数组位置关联，不支持每道独立外部 `process_id`。两道及以上必须使用 `global_process.coplanarity_check_mode=1`，该模式计算多道偏移；自由模式 0 不计算偏移，模式 2 需要组合焊缝和多坐标系结构，不在本 mapper 范围。示例 path 严格使用 RobotBase/mm/XYZ Euler(w,p,r)/degree；SDK 不转换姿态或角度，也不创建或校准坐标系。非法数值、非有限值、空数组和未知字段应明确拒绝或报告不支持。
输出 project.direct_run=0, loop_execution=0, need_digital_start=0, need_reservation=0, execution_mode=1, task_source=0；MCS_WorkpieceTask含`global_process`、workpiece_type=0、laser_task_type=0、scanning_welding=0、scanning_mode=0、tracker_type=2、weld_process_id=0及明确id/robot_tcp_id/workpiece_db_id；每seam变为node，is_multi=true、multi_layer_num=max(layer)（运行期会重算，不能作层语义依据）、multi_pass_num=N、weld_process_id=process_id、path保留6轴值/生成point uid/valid=true、multi_pass_params用实际MCS_MultiPass字段（multi_offset_mode=0,multi_offset_x=0）。不提交weld_package。不伪造安全生产工艺。
实际服务端会DB覆盖node.weld_process，再合入node.multi_pass_params；multi_layer_num重算sqrt(2*N)，层元数据见每道layer_index，不依赖聚合层数执行。process_vec长度和DB multi_pass_params长度必须满足N；在显式提交前先process_detail检查，服务端仍负责最终校验/规划。数组顺序主导process_vec[i]/偏移[i]，multi_index不是任意排序键。

## 示例安全入口
`basic` 默认只展示协议，`--connect` 启用查询。`multipass` 默认转换、校验并输出 JSON；只有 `--execute` 和有效输入同时提供时才提交。即使 `direct_run=0`，提交仍会触发服务端预检和规划。start/pause/continue/stop 使用独立的显式 control 子命令，不能在普通示例中按时间自动循环控制。Action 进程持有句柄并处理反馈和结果，另一进程只执行 control；恢复时只查询状态并比对当前工程 UID，不自动重发。点云示例使用 `camera-cloud` 显式 download，将分块写入 NDJSON sink，并检查序号和 `total_blocks`。反馈时间戳保留原值；接口未指定单位时不做换算。

## Task 取消与受理
Task cancel 返回 ACCEPT，但不执行完整任务停止。`ActionOperation.cancel()` 只提供 ROS cancel 响应；停止任务必须调用 `task_destroy`，随后观察业务状态和设备状态。析构时不得自动 cancel。`accepted=true` 仅表示 ROS Goal 已接纳；任务准备状态还需检查 101002/101007 和当前 UID。
- 工艺顺序约束：数据库查询不保证 `process_vec` 排序，执行逻辑按返回数组下标使用工艺。提交前必须逐位置检查 `process_vec` 的 order 与输入 index；不一致时拒绝执行。SDK 不得先在本地排序再假设服务端使用同一顺序。回读与提交不是原子操作，期间不得由其他调用方修改工艺。

- 执行前必须逐项检查 `process_vec[i].weld_bead_process_order == passes[i].index`、`layer_num == layer`、`bead_num` 等于该层内从 1 开始的输入序号，以及数据库 `multi_pass_params[i].multi_index/layer_index` 和数组长度。字段缺失、顺序错乱或层道错配时拒绝执行。回读与提交不是原子操作，执行期间应冻结工艺配置。

APP点云文件下载不使用SDK的ROS调用，见[HTTP点云下载](point-cloud-download.md)。
