# 3D相机扫描作业：只扫描、不立即焊接

没有独立的扫描Action。扫描作业复用 `/at/task/task_action`，类型 `weld_interfaces/action/ATWeldTask`；Goal只有字符串字段 `json_data`，内部仍为 `project + workpieces[]`。本节是该接口的**3D扫描模式**，不是新增通信协议。

示例环境没有 3D 相机当前配置或手眼标定，因此本页只提供请求结构，不提供成功扫描结果。任务接收会清理既有日志、覆盖当前任务缓存并占用任务资源；未满足相机、标定、TCP、工艺、路径和现场安全条件时不得下发。

## 两个开关不能混淆

|字段|只扫描参考值|实际含义|
|---|---|---|
|project.direct_run|整数0|仅接收/分析后等待；direct_run=0不会开始扫描|
|project.loop_execution|整数0|非循环；不重复扫描/执行|
|project.need_reservation / need_digital_start|整数0|本例不启用预约或外部IO启动|
|workpieces[].planning_mode|整数0|普通作业分支；planning_mode=1不能保证不焊接|
|workpieces[].laser_task_type|整数1|扫描；0不启用，2寻位|
|workpieces[].tracker_type|整数1|3D相机；0线激光，2无传感器|
|workpieces[].scanning_mode|整数1|定点扫描；0为一键扫描。与APP示教点往返一致，后端实际路径来自scanning_feature_points|
|workpieces[].scanning_welding|整数1|扫描/生成路径后不立即焊接；0会走扫立焊分支|

必须让工程中**每个工件**都符合上述只扫描条件，不能混入普通焊接工件。仅设置scanning_welding=1或direct_run=0都不能替代完整条件。

“立即启动”和“立即焊接”是两回事：若以后明确允许下发后立即执行扫描，可把direct_run设为1，同时保持全部只扫描条件；这会直接触发机器人/相机作业，不是单纯保存。本页仍显式使用0，之后的启动也是单独的设备执行操作。

`post_scan_welding`、`need_confirm_after_scanning`、`need_confirm_after_planning`：扩展字段，当前版本未使用，可不填。不能用它们保证扫描后等待或阻止焊接。

## 设置扫描路径与必要关联

扫描点放在 **workpieces[].scanning_feature_points**，不是nodes[].path，也不是get_workpiece_scan_path的请求参数。`scanning_fixed_point`是另一组矩形示教/特征点，本例留空。当前不支持就地更新扫描路径，task_workpieces_update不提供更新功能。

|点字段|类型、单位与填写|
|---|---|
|x / y / z|number，基座TCP位置，mm|
|w / p / r|number；当前Aubo分别对应rx/ry/rz，ZYX欧拉角rad，不是degree|
|uid|string，点唯一标识|
|valid|boolean；本例true，当前扫描执行未读取此标记|
|type|整数：0 开始、1 中间、2 结束、3 空跑直线。4 和 5 不属于本示例支持范围。|
|weld|string，预留关联标识，本例空字符串|

单点扫描只能用一个START；多点需START → MID… → END，空跑直线点可穿插。3D执行是**逐点到位后采集**，不是边运动边连续曝光；多于一个扫描点时拼接多次点云。当前Aubo姿态矩阵为Rz(rz)×Ry(ry)×Rx(rx)。不要将此约定推广到其他品牌。

此外必须提供正确的 `weld_process_id`、`robot_tcp_id`：扫描前会切换TCP；扫描速度取关联工艺第一道的 `positioning_motion_params.positioning_speed`，空跑速度取 `welding_motion_params.safe_speed`（本文START/MID/END及空跑直线分支为mm/s；空跑关节分支不适用），3D任务号取 `camera_tracking_params.job_num`。再按任务号读取相机配置、算法参数与手眼标定；这些不是Goal里随意增加的camera_ip/扫描速度字段。

## 完整Goal结构与调用顺序

下载[完整扫描 JSON](../docs/scan-only-goal.json)。示例以位置快照为 START，END 仅增加 X 10 mm；引用示例工艺 114 和 TCP 1，工程与工件 ID 为 0，不写数据库。部署时必须替换全部业务 ID 和路径，并完成可达性、碰撞、坐标系及扫描范围检查。

示例工艺114的track_3d_id/hand_eye_calibration_id为0，且示例环境未配置3D相机；此JSON仅说明完整请求结构，不可在该配置下直接启动扫描。

1. 确认相机配置、TCP、手眼标定、扫描工艺、当前任务占用和安全环境。
2. 使用任务Action下发完整JSON，显式direct_run=0。此时只等待，不采集。
3. 只有允许机器人扫描运动的独立执行阶段，才调用任务Service的task_start。它会启动整个已接收工程，不是“仅接收”指令。未满足设备、标定和安全前置条件时禁止调用。
4. 持续读取Action反馈/任务状态；扫描后用路径查询读取生成结果。
5. 确认当前扫描生成的点云文件已更新，再通过 HTTP 下载。

本地只构造ROS Goal，不联网：

```bash
export SCAN_JSON=/path/to/atweldsystem-api/docs/scan-only-goal.json
python3 - <<'PY'
import json, os
task=json.load(open(os.environ['SCAN_JSON']))
assert type(task['project']['direct_run']) is int and task['project']['direct_run']==0
assert type(task['project']['loop_execution']) is int and task['project']['loop_execution']==0
for wp in task['workpieces']:
    assert all(type(wp[k]) is int and wp[k]==v for k,v in {
        'planning_mode':0, 'laser_task_type':1, 'tracker_type':1, 'scanning_welding':1
    }.items())
print(json.dumps({'json_data':json.dumps(task,ensure_ascii=False)},ensure_ascii=False))
PY
# 仅说明命令形状；示例环境不满足执行条件，不得执行：
# ros2 action send_goal /at/task/task_action weld_interfaces/action/ATWeldTask '<上方Goal JSON>'
```

启动扫描的请求格式：Service `/at/task/task_services`，`weld_interfaces/srv/ATStringGeneric`：

```json
{"id":"","data":"{\"service_name\":\"task_start\"}"}
```

任务接收阶段可能同步焊机配置并写入缓存；启动后还会执行公共配置同步、机器人准备、TCP 切换、机器人运动和相机采集控制。**不进入焊接分支不等于没有设备副作用。** 即使本例不焊接，也必须满足任务下发和机器人运动的全部安全条件。

## 状态与结果判断

反馈JSON中的状态码为字符串：

|字段/值|含义|
|---|---|
|project_status=101001 / 101002|分析中 / 分析完成|
|project_status=101007|等待启动；尚未实际扫描|
|project_status=101003|运行中|
|workpiece_status=102002 / 102003 / 102004|扫描中 / 扫描成功 / 扫描失败|
|workpiece_status=102006 / 102007|扫描后路径规划成功 / 失败|
|project_status=101006|工程结束；还要结合Action终态及工件结果|

仅Goal接收成功或启动Service返回200，不证明采集成功。只扫描流程成功应结合102003、随后102006及Action成功终态/101006判断，**不是焊接运行成功**。几何提取/规划失败也不等于从未采集到点云。

## 查询生成路径与下载点云

路径查询为**只读**：`/at/task/task_services`，`weld_interfaces/srv/ATStringGeneric`：

```json
{"id":"","data":"{\"service_name\":\"get_workpiece_scan_path\"}"}
```

status=200后解析data字符串，得到当前任务workpieces数组；按uid匹配工件，再读取nodes及规划结果，不按数组下标或数据库ID拼接。这个查询不会设置路径或触发扫描。

点云下载沿用APP实际HTTP入口：

```bash
curl --fail --show-error --output world.pcd 'http://192.168.1.101:10001/download/world.pcd'
```

响应为 PCD 字节，不是 JSON；HTTP 200 后还要解析 PCD。404 表示文件不存在。文件名固定且接口不绑定任务 ID，200 不能证明文件属于当前扫描；必须结合扫描状态、文件更新时间和内容确认，避免显示上一任务的缓存点云。

底层 `/at/scan/control` 负责采集/算法命令，不承载机器人路径；自动作业会自行编排它。`/at/scan/get_result`用于算法结果，`/at/scan/get_point_cloud`不是APP的文件下载链。本节不要求外部调用方手工交错底层命令，也不恢复已退役的ROS点云下载入口。
