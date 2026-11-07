# 自动作业 Python 脚本

`auto_task.py` 使用仓库原生 `from aotai_sdk import Client`，通过 ROS 2 DDS 调用
`/at/task/task_action` 和 `/at/task/task_services`，不是 SSH，也不是 9090 rosbridge。
脚本无需每次输入主机密码，也不用 pip 安装本仓库 SDK。在线执行仍需 ROS 2/rclpy 和
匹配的 weld_interfaces；Windows 普通 Python 只能运行帮助和离线检查。当前建议在已配置的
Ubuntu 虚拟机运行。IP 不作为 Client 参数，DDS 网络、ROS_DOMAIN_ID 必须匹配服务端。

## 1. 当前机器运行

```bash
cd /home/rosadmin/whc/develop_test
source verification/python-sdk-manual/setup_local_sdk.bash
python3 atweldsystemapi/examples/python/auto_task.py status
```

这里的 setup 脚本属于当前测试工作区，不在发布 ZIP 内。其他机器至少需先 source
`/opt/ros/humble/setup.bash`、自己工作区的 weld_interfaces 环境，并按部署配置 DDS 网络。
**不需要把脚本放到 192.168.1.101 上**，但本机必须能发现那里的 ROS 服务。

## 2. 先离线试跑

```bash
python3 atweldsystemapi/examples/python/auto_task.py check
python3 atweldsystemapi/examples/python/auto_task.py check --input /绝对路径/真实任务.json
```

无参数只显示帮助，`check` 不连接设备。未指定文件时只检查仓库演示 JSON，**演示任务禁止下发**。
不能仅改演示名称就认为坐标安全，也不要使用之前临时创建的数据库测试工程直接运行。

输入必须是完整任务 Goal 内容：`{"project": {...}, "workpieces": [...]}`，或外层
`{"json_data": "上述对象的JSON字符串"}`。只填工程 ID、数据库 detail 响应、或
`examples/data/multipass-input.json` 映射器输入，都不能直接当成任务 Goal。
本脚本不编辑工程、不生成轨迹、不自动选择工艺/TCP。请使用已审核的真实任务 JSON；
字段参考 [扫描流程](../../docs/scan-only-workflow.md)、[任务状态](../../docs/task-states.md)。

必须明确填整数 `0`：`project.direct_run`、`loop_execution`、`need_reservation`、
`need_digital_start`。每个工件提供真实 `robot_tcp_id`、`weld_process_id`、唯一 uid、
`nodes` 数组和相应任务字段。扫描轨迹位于 `scanning_feature_points`。
脚本只做基础结构检查，不保证全部业务字段、工艺存在、碰撞、速度或坐标系正确。

## 3. 下发但不自动启动（终端一）

**下发本身有副作用**：可能清理旧任务日志/焊接数据、覆盖临时任务、占用资源及准备设备。
`direct_run=0` 不是纯校验，也不保证没有设备配置操作。
必须已审核真实路径、坐标系、速度、TCP、工艺，现场有人监护急停，并保证只有一个控制方。
下面 `YOUR_UID` 替换为文件中的 `project.uid`；每次新任务用新的 UID，但服务端并不提供去重保证。

```bash
python3 atweldsystemapi/examples/python/auto_task.py submit \
  --input /绝对路径/真实任务.json --expected-uid YOUR_UID \
  --confirm-data-reset --confirm-site-safe --wait 600
```

脚本保持连接并打印反馈。ROS `accepted` 只是受理；`101007` 表示等待启动。
已有未完成/未知状态任务会拒绝覆盖，不自动暂停、销毁、重试或上下电。
空状态 `{}` 不证明空闲或安全，必须结合现场确认。

## 4. 明确启动（终端二）

在另一个已 source 同样环境的终端操作；仅在反馈 `101007` 且工程 UID 匹配时启动：

```bash
cd /home/rosadmin/whc/develop_test
source verification/python-sdk-manual/setup_local_sdk.bash
python3 atweldsystemapi/examples/python/auto_task.py start \
  --expected-uid YOUR_UID --confirm-site-safe
```

**这一步可能真实运动、扫描或焊接，取决于任务配置，脚本不强制“只扫描”。**
若只扫描，必须逐工件核对扫描专用参数并在现场禁焊，见扫描流程文档。
UID 回读不是锁，服务端启动接口控制的是全局当前任务，禁止其他客户端同时切换任务。
启动响应 200 不代表执行完成；终端一仅在 ROS SUCCEEDED 且业务 `101006` 时报告正常完成。

## 5. 超时或断线

Ctrl+C、等待超时、SDK 关闭及 Action cancel **都不会保证停止设备**。
先现场检查并用 `status` 查询，**不要重复 submit**；本脚本没有自动恢复、自动重发或自动停止。
需停止时优先执行现场安全流程，软件暂停/销毁响应也不是机械停稳证明。

验证范围：离线回归与本机隔离 ROS mock；未用本脚本下发真实作业。无任何真实运动验证结论。

## 执行结果不能只看成功码

此通用客户端的 Action 结果检查不提供机器人最终位姿或焊缝质量验收。集成方还必须核对同 UID、故障/暂停历史、设备静止和预规划最终目标；`SUCCEEDED + 101006` 不足以单独证明物理完成。焊缝、工艺及异常恢复说明见[自动作业流程](../../docs/task-states.md)。
