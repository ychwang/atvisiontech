# 多层多道数据与使用限制

## 可持久化的工艺层数据

工艺聚合中的 `multi_pass_params` 是数组，存入 `at_weld_system_multi_param.parameter_json`。每项对应 `MCS_MultiPass`：

```json
{
  "multi_index": 1,
  "layer_index": 1,
  "multi_offset_horizontal": 0.0,
  "multi_offset_vertical": 0.0,
  "multi_offset_start": 0.0,
  "multi_offset_end": 0.0,
  "multi_dir_horizontal": 0,
  "multi_dir_vertical": 0,
  "multi_dir_forward": 0,
  "multi_offset_dir_end": 0,
  "multi_offset_mode": 0,
  "multi_offset_x": 0.0,
  "weld_layer": -1
}
```

所有 offset 的单位为 **mm**。常规模式横向右偏为正、竖向 Z+ 为正；`multi_index` 和 `layer_index` 从 1 开始。该 JSON 只表达多层多道偏移，不携带独立轨迹点、TCP 姿态或点云。

工艺 `process_vec` 每道还必须表达 `weld_bead_process_order`、`layer_num`、`bead_num` 与对应参数子对象。服务端会把三者写到 `at_weld_system_process_to_weld_bead_assoc`。**读取 SQL 不含 `ORDER BY`**，尽管注释提示 APP 按 `weld_bead_process_order` 排序；第三方不得自行排序后宣称服务端会同样排序；应回读并逐位置核对 `weld_bead_process_order`（全局 `index`）、`layer_num` 与提交 `layer`、以及 `bead_num`（同一 layer 内按输入顺序从 1 开始）的一一对应。任何错配、缺失或顺序未知均 fail-closed，拒绝进入执行。

## 与工程的引用关系

`workpieces[].global_process` 不能省略。示例将其完整传入 `MCS_WorkpieceTask` JSON；`coplanarity_check_mode=1` 是单一平面直线多层多道的前置条件，该模式计算多道偏移。模式 0 使用自由模式且不计算偏移，模式 2 需要多坐标系和组合焊缝结构，不在本 SDK 单直线输入范围。因此，两道及以上输入只接受模式 1；调用方仍须确认坐标系和共面条件。

本 mapper 固定只接受 `coordinate_contract.frame="RobotBase"`、`position_unit="mm"`、`orientation_convention="XYZ Euler: w,p,r"`、`angle_unit="degree"`；这只是此 mapper 的输入限制，不证明机器人 get_pos 的实际格式（有驱动可能输出 rad）。`confirmed=false`、演示 ID 为 0，默认不可执行；即使设为 true 也不会允许其它格式。现场执行前第三方须完成转换并确认同一平面、机器人 TCP/坐标系与实际工艺；SDK 不创建、不标定也不查询工件坐标系。`w/p/r` 原样传递，不由 mapper 转换角度或姿态。

1. 用 `/at/data/process_add`（或已有工艺）取得 process ID。
2. 工件模板 `welds` 的每项 `weld_process_job_nob` 按 **process ID** 建立引用，名字不是安全的 job_num 语义。
3. 工程 JSON 每个 workpiece 的 `weld_process_id` 与每个 `nodes[].weld_process_id` 也被收集为 process ID 关联。
4. `/at/data/workpiece_task_add` 只保存该工程定义，不把任意排道数据转换成运行轨迹，也不开始执行。

## 严格兼容限制

数据库工程 JSON 不保存 `touch_sensing_config` 或 `weld_package`；任务 Action JSON 可以包含 `planning_mode` 和 `touch_sensing_config`。因此，从数据库保存并回读的工程不能无损承载触碰寻位、运动规划模式或规划结果。需要这些字段时，应按任务 Action 结构单独构造请求。

运行时按 `node.weld_process_id` 查询数据库工艺详情并覆盖 `node.weld_process`，因此该路径使用工艺引用，不使用客户端提交的工艺快照。SDK mapper 只接受 RobotBase 下两点直线和每道偏移，不接受每道独立外部轨迹、组合或非共面多坐标系排道，也不允许客户端覆盖焊接姿态。下发必须使用 `/at/task/task_action` 的 `json_data` 和任务 Action 结构。

## 完整接入示例（只构造/校验，显式执行）

1. 第三方输入每条焊缝的稳定 `node.uid`、RobotBase 下六轴路径点、`weld_process_id`，每道偏移和 `workpiece.global_process`。SDK 的输入 `passes[].index/layer` 映射到 MCS `multi_index/layer_index`；工艺回读中还必须逐位置核对全局 `weld_bead_process_order`、`layer_num` 和同层递增的 `bead_num`。两道及以上时输入 `global_process.coplanarity_check_mode` 必须为 1；偏移值按 mm 填入 `multi_pass_params`。
2. 先保存或查询工艺，随后用 `/at/data/process_detail` 的 `id` 回读。**不排序**：按返回的原始 `process_vec[i]` 逐位置比对输入的 order/layer/bead 与 `multi_pass_params[i]` 的 multi/layer；任一缺失、长度不同或错配即拒绝生成可执行 Action Goal。
3. 构造应用侧 `ATWeldTask` Goal：`{"json_data":"<MCS_WeldTask JSON>"}`。这不是数据库 CRUD；若 payload 需 `planning_mode`/`touch_sensing_config`，只可走 Action 应用侧 serializer，不能期待 `workpiece_task_*` 保存后仍保留。
4. `multipass.py` / `aotai_cpp_multipass` 默认只做本地 schema 组装并打印 JSON，不连接 ROS、也不回读工艺。只有显式 `--execute` 才会按第 1–2 步回读工艺、核验数组、提交 `/at/task/task_action` 并等待 Action result；这条路径可能触发预规划/作业，不能用于普通格式检查。
5. 开始、暂停、继续、停止必须在另一个显式控制终端完成，并按[任务状态与控制](task-states.md)的状态和 UID 步骤执行：Python `control.py task_start|task_pause|task_continue|task_destroy --expected-uid UID`，C++ `aotai_cpp_control start|pause|continue|stop UID`。`task_destroy` 将状态置为 stop-cancel 并异步尝试禁用焊机；Action cancel 不是停止。服务响应不表示机械已经停止或焊缝已经完成，执行前必须完成目标环境的业务数据、设备和安全条件验收。
