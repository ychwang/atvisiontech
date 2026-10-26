# 接口依赖与接入顺序

工艺分组、工件分组、设备配置与运行状态查询构成后续操作的前置条件。先从查询结果取得当前环境的真实 ID，再按下列顺序调用。

## 工艺分组 → 工艺 → 焊道

1. [查询分组](#process_class_list)或[创建分组](#process_class_add)，取得真实**分组行ID**。`class_job_num`是业务号，不能替代外键。
2. [创建工艺](#process_add)的`data.class_id`指向该行；完整嵌套工艺聚合不是只传名称和电流。[查询详情](#process_detail)不能无转换原样回写。
3. [按分组列工艺](#process_list_by_class)取得工艺行ID；需要移组用[修改关联](#process_class_assoc_update)，不是重建或复制工艺。
4. 焊道关联遵循[公共工艺/工程字段](field-data-contracts.md)。先检查已保存工程的引用；查询不保证运行时任务已释放引用。
5. [删除工艺](#process_delete)后再[删除普通分组](#process_class_delete)；普通组仍有活动工艺会拒绝。默认组另走受控软删除级联，不能拿它当通用清理手段。

[工艺分组与工艺调用流程](process-workflow.md)提供准确的写入字段和示例。完整工艺必须使用当前写入结构；程序不会为缺失的聚合字段、配置 ID 或业务枚举补造值。

## 工件组 → 工件模板 → 工程实例

[工件分组查询/创建](#workpiece_group_add)取得行ID → [工件新增](#workpiece_add)`data.group_id` → [详情](#workpiece_detail)核对焊缝/焊道 → 组装工程实例与任务。

- [分组详情](#workpiece_group_detail)外部filter键是`id`，不是`group_id`；group_id不作为请求键。
- [组更新](#workpiece_group_update)有已知错误分支返回200并带错误message，不能仅凭status继续。两语言模块程序拒绝非空message并中止清理。
- [删组](#workpiece_group_delete)软删除组及关联模板，不提供工程实例级联清理保证。
- [工件分组模块示例](workpiece-group-workflow.md)使用示例名称 `分组-1`、`66`；示例 ID 6/7 必须替换为创建接口返回的 ID。

## 设备与任务

|模块|已有必要接口及顺序|仍不能据此保证|
|---|---|---|
|机器人|init→[get_config](#robot_config)核对运行时选择→connect→状态/位姿→明确运动命令→运动完成反馈/状态→停止|初始化不表示上电或到位；子型号必填。坐标、单位、速度和安全范围按目标驱动确认。|
|焊机|查询协议/当前配置→下发完整配置→connect→准备信号/参数→enable门控→显式焊接命令→弧状态回读→结束/清门控|配置必须包含目标型号要求的量程与模式；示例参数不能直接作为生产焊接参数。|
|相机/点云|相机配置与连接→扫描任务→状态/采集结果→HTTP 点云下载|3D 相机 GUID、手眼标定、TCP 和扫描工艺均为前置条件；下载接口不会启动扫描。|
|自动作业|准备工程/工件/工艺及设备→Action受理→task_start→feedback/task_status→终态；暂停/继续/停止按任务状态门禁|Service 200 不等于任务完成；[current_task](#task_current)仅返回当前缓存任务，不是运行反馈。业务 ID 不可跨环境复用。|
|多层多道|第三方路径转换为工程/焊道结构并关联工艺→回读并逐位置校验→任务Action→反馈/结果|仅支持文档列出的坐标契约和结构；不支持任意第三方轨迹直传。执行前必须完成工艺顺序、坐标、单位和设备验收。|

## 配置、查询与运行态的依赖

### 持久配置不是运行态控制

- 焊机/机器人/线激光/3D相机：同族 `list → detail` 取得当前数据库行和设备值；`add/update` 是数据库写入，`set_default` 切换当前项，部分还触发同步。`current_detail` 返回当前配置；不能把它等同设备已经连接或生效。
- TCP、手眼标定、负载：`list/detail → set_default → current` 管理存储记录；实际机器人 `tcp_offset/setload` 或相机标定接口是另一层设备操作。表内TEXT数值不等于ROS float64，也不自动定义单位。
- [焊机协议](#welder_protocol)和[机器人协议](#robot_protocol)提供配置选项；协议允许值、当前选择和设备允许值应分别判断，不把示例 IP、型号或 ID 写成固定默认。
- 所有新建/更新示例仅为接口结构示例；必须从同族列表取得行ID，不跨表复用，更不能把成功保存当成已完成现场标定。

### 工艺业务号与行ID

1. [分组列表](#process_class_list)与[分组业务号](#process_class_job_num_list)获取当前数据。
2. [按业务号查分组](#process_class_detail_by_job)使用 `class_job_num`；[按业务号查工艺](#process_detail_by_job)使用 `class_job_num + job_num`，不是数据库行ID。
3. [分组计数](#process_count_by_class)返回动态键对象：**分组行ID文本 → 计数字符串**，不是业务号到整数。
4. [页面参数字典](#process_page_config_get)返回 `pageConfigs/paramConfigs`，其中最小/最大/默认值是配置元数据，不是实际焊接数据；与早期接口说明 `process/processParam/processVec` 结构有差异。
5. 工艺/模板删除前可读 [工艺引用数](#process_used_count_query) / [工件引用数](#workpiece_used_count_query)；0只说明当前查询结果，不是自动删除授权。

### 线激光与3D相机分开

线激光 `search → sensor_search_result → config(connectSensor) → control/position → measure/图像` 是独立链路，不能套用3D相机 `command_type`：线激光配置用 `commandType`，定位用 `COMMAND/INFO`。

只有线激光 `config(connectStatus)` 是缓存查询分支，不能将整个config/control/position或search当作无副作用查询。3D相机 `get_eye_images` 虽名为get，调用会切换SDK采集模式，也**不是无副作用查询**。被动Topic订阅不自动启用传感器。

### 暂停回退与占位操作

暂停后可按“[设置回退距离](#task_retreat_set) → [读取回退距离](#task_retreat_get) → [继续](#task_continue)”调用。距离在特定焊接恢复路径消费后清零。APP 的 5 mm 默认值和 0–20 mm 范围属于界面策略，不是服务端接口的范围校验。

`task_start_workpiece`、`task_workpieces_update` 不提供单工件启动或工件更新功能，不可用于任务执行流程。`get_workpiece_scan_path` / `get_workpiece_plan_path` 读取已有任务路径，不触发扫描，且需有效任务线程。

### 机器人配置、系统告警与标定

- [碰撞等级](#robot_collision_level_get)/[停止方式](#robot_collision_stop_type_get)/[当前阻尼](#robot_freedrive_damp_get)与对应设置配套；写端先改数据库再下发驱动，驱动失败不保证数据库回滚。读取status=200仍需校验返回值域。
- [初始阻尼](#robot_initial_freedrive_damp_get)、[预置姿态](#robot_position_get)、[运动配置](#robot_motion_get)读取默认/当前配置，不是实时运动反馈；坐标切换影响后续输入解释。
- [系统状态Topic](#system_status_topic)观察设备/任务JSON；从独立[告警码Topic](#system_alarm_topic)按逗号成对解析取得真实报警码 → [报警详情](#system_alarm_detail_query)及处理建议 → 在明确授权下才考虑[复位](#system_alarm_reset)，每项reset_ok分别判断。当前失败项也会清除内存提示、空告警集合不发布，提示消失不是设备故障已解除。复位和[急停](#system_emergency_stop)只能用于具备相应权限及安全条件的设备控制。
- [标定板信息](#camera_calib_board_detect_info)会切换SDK独占操作并关闭strobe，不属于只读采样白名单；[手眼计算](#camera_hand_eye_calibration)依赖真实点集/姿态，返回矩阵不等于已经持久化或现场验收。
- [版本查询](#robot_version_get)与[升级 Action](#robot_version_update)风险不同；升级会传输文件并执行远程安装，且不支持 cancel。查询版本不触发升级。
- [焊接记录](#task_welding_data_get)按页查询。`resolution`：**扩展字段，当前版本未使用，可不填。** 数组长度以本页 `timestamp` 核对，不把 `total` 当成本页数据量。

### 同型机器人接口的两层语义

`/at/data/robot_*` 是数据库配置接口，不下发机器人驱动；`/at/robot/*` 是运行层接口，部分会先写库再调用设备，不能仅凭Service类型相同互换路径。

- 碰撞等级、停止方式、当前阻尼：数据库get取得存储值；运行层get读取驱动。DB写成功不代表驱动已应用。
- 预置姿态、运动参数：`type/is_default`选择存储记录，必须先读取再修改，物理单位与安全值须设备侧确认。
- [DB motion V2](#robot_db_motion_set)无条件写全部11字段，0/负数也进入更新；[运行层motion](#robot_motion_set)只将正数字段纳入部分更新。不得将默认0当作DB层的“未填写”。

## 填写参数与解析返回值

- **界面数值不等于协议数值**：机器人速度25%发送0.25；拖动阻尼按关节1..6发送6个比例值，不能发送页面百分数。页面范围与服务端校验、驱动支持范围分别按接口说明判断。
- **工艺筛选**：filters是KeyValue数组，value为字符串；空筛选项省略。排序字段显式填写id或job_num，不能留空。更换筛选条件时从第1页重新查，解析内层data数组和total总数。
- **工程保存与另存为**：先把界面树转换为工程聚合，顶层name与project.name保持一致；更新使用数据库project.id，另存为不要沿用原行ID。运行uid不是数据库行ID。
- **保存响应回填**：先检查业务状态，再解析data；project_id是工程行ID，workpieceIds按输入工件顺序回填，不排序、不替换运行uid。保存成功不等于任务已下发。
- **扫描路径匹配**：返回data是工件JSON数组，以工件uid匹配当前已下发对象，再检查nodes；不能按数据库id或数组下标拼接到任意工件。
- **界面字符串不等于协议枚举**：焊机页面的 `tcp_status` 不是当前服务端支持键；碰撞等级 10 出现在 APP 选项中，也不表示目标驱动支持该值。遇到冲突时按接口允许值和目标驱动配置处理，不自动重试控制请求。
