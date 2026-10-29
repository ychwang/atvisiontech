# AOTAI 第三方接口调用约定

本协议说明各接口的公共调用约定。它们是 ROS 2 名称，**不是 HTTP REST**；rosbridge 仅在部署了对应桥接器时可将 ROS 消息编码为 JSON，不能改变下列字段、服务名或状态语义。

## 通用规则

1. 先等待服务/Action server 或订阅 Topic，再发请求。ROS 调用成功只表示请求响应抵达；业务成功须检查响应的 `status`、`message` 及业务字段。
2. 数据库 `ATStringGeneric`：请求有 `id` 与 `data` 两个 string。`process_detail`、`process_multi_param_get`、`workpiece_task_detail` 的 ID 必须放 `id`；`data` 不会替代它。创建/更新的聚合 JSON 放 `data`。
3. 数据库状态枚举：`200` 成功、`400` 业务/参数错误、`500` 异常。错误信息在 `message`；不得用 HTTP 状态码替代。
4. 控制类服务（机器人运动、焊接开关、送退丝、供气、相机控制）不会自动重试。通信超时后先读状态/日志，不能断定命令未实际执行。
5. 所有示例均只说明字段形状：设备地址使用 TEST-NET，电流/电压及轨迹不构成真机参数；示例没有自动调用危险端点。

## 机器人

核心链路：`/at/robot/init_robot` → `/at/robot/connect` → `/at/robot/status` 或实时状态 Topic → （必要时）显式运动 → `/at/robot/move_stop`。运动前应由集成方保证安全区、急停、互锁、上电和驱动状态；停止响应不等于机械已停稳，必须以状态反馈确认。

已目录化端点包括初始化、连接、状态、当前位置、步进/连续/直线/关节运动及 `move_stop`/`stop_line`。位姿坐标系、姿态表示和单位必须以相应 `.srv` 字段和实际机器人驱动为准；当前目录不把名称猜成 mm、m、欧拉角或四元数。`/at/robot/get_real_time_status` 是观察 Topic，客户端应处理断流与订阅释放。

## 焊机

先连接焊机，再查询状态/实时 Topic；设电流电压不是起弧。`/at/welder/welding`、送丝、退丝、供气属于危险显式入口，必须由应用层再次确认，不得因网络错误重试。`/at/welder/welder_realtime_data` 是 100 ms 周期 Topic（服务接口常量），没有命令确认或补发。不同焊机型号的模式值/量纲由驱动决定。

## 3D 相机与点云

`camera_node` 使用私有名称，默认节点命名空间为 `/at`。相机配置、控制、搜索和状态仍使用对应ROS接口；搜索结果在 `sensor_search_result` Topic发布，状态为JSON字符串。

APP点云文件使用[HTTP下载](point-cloud-download.md)：`GET http://<系统主机 IP>:10001/download/world.pcd`，响应为PCD附件，不是ROS消息或JSON。ROS点云Topic仅用于对应流式观察，不是APP的文件下载方式。`ATPointCloud`本身没有frame_id字段，不能把节点frame_id参数当作每帧携带的坐标信息；文件坐标含义与单位仍需匹配扫描配置。

## 工艺、工程与任务

`/at/data/process_*`、`/at/data/workpiece_*`、`/at/data/workpiece_task_*` 是数据库 CRUD。`workpiece_task_add` 存储工程/工件 JSON，不投递执行器；成功只表示保存。`/at/task/task_services` 的 `data` 是 JSON，`service_name` 可使用 `get_task_status`、`task_start`、`task_pause`、`task_continue`、`task_destroy`；状态前置条件和停止时的异步焊机禁用见接口卡片。完整下发使用 `/at/task/task_action` (`ATWeldTask` Action)，Goal 的唯一顶层字段是 `json_data`。Action 接受不等于执行完成，必须消费 feedback/result。运行时会按 `node.weld_process_id` 读取工艺详情并写入 `node.weld_process`，下发前需逐位置核对工艺顺序。


### 相机配置/控制 JSON

`LaserConfig` 的唯一请求字段是 `config_str`，必须是 JSON object 字符串；非法 JSON 时其 `message` 返回 `{"status":400,"message":"Invalid JSON"}`。`LaserControl.control_str` 也必须是 JSON object；命令为 `{"command_type":"start_capture"}` 与 `{"command_type":"stop_capture"}`。两种服务的 ROS response **只有 `message` string，没有顶层 `status`**；客户端必须解析其内层 JSON `status/message`，不能访问不存在的 `response.status`。

`points_raw` 的 `ATPointCloud` 包含 `seam_point`、`points` 和 `timestamp`。当前版本不保证 `timestamp` 的来源和单位；不要用消息到达时间或 status JSON 代替采集时间。

### Aubo 位姿限制

`/at/robot/get_pos` 仅在机器人连接后读取 `cur_pos`、`joint_pos`、`flan_pos`，并要求三个数组长度为 6。正常响应不使用通用的 `status==200`，客户端应检查连接状态、三个 6 元素数组及错误消息。Aubo 的前三项位置以 mm 返回，后三项姿态以 rad 返回；此单位约定不能推广到其他驱动。有效范围由目标型号和设备安全限制决定。

## 公共调用与字段约定（各接口只写例外）

- **必填与默认**：ROS 消息可以省略字段并得到类型零值或空值；这不表示业务字段可省略，也不表示零值安全。接口参数表说明服务读取、忽略、校验或透传的字段。未提供统一业务范围的字段只保留适用限制，不扩展为全型号枚举。
- **并发**：SDK 同步方法由调用线程使用，反馈和订阅在后台 executor 回调；回调中不要同步调用 SDK。设备和当前任务写操作由集成方串行化；服务端没有统一的请求幂等键或任务所有权锁，不支持多个客户端并发控制同一设备或任务。
- **超时**：显式设置等待服务、请求响应和 Action 终态的超时；未收到响应属于通信结果未知，不是请求被拒绝，更不代表设备停止。两语言可传显式超时，默认值见各 SDK 签名。Action 接纳等待与终态等待分别设置。
- **错误**：Python checked call 对已识别的 status 抛出拒绝/服务端错误并保留原响应；C++ typed call 返回原始响应，由调用者按该接口成功条件判断。相机服务成功码位于 `message` 的 JSON 内；机器人 get_pos 的 0 特例只对该接口成立。原始驱动 `result`、message 不丢弃，不能把所有 200 当作运动/起弧完成。
- **断联与重连**：释放订阅、关闭 SDK 只清理客户端资源；不会取消或停止服务端作业。恢复连接后先读任务状态和当前 project.uid，再核对设备；不自动重发运动、起弧、工程保存或任务。服务端缺少既有任务结果/幂等查询时，无法从超时推断恢复方案。
