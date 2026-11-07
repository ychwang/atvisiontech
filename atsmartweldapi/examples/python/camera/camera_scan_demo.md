# 单台3D相机完整扫描 Demo

脚本：[camera_scan_demo.py](camera_scan_demo.py)。直接运行，无命令行参数；配置常量在文件开头。系统主机为192.168.1.101，本机网卡为192.168.1.252，由 `_common.py` 和随包XML配置；相机自身IP为192.168.1.20。

本例只控制3D相机及其摆动机构，不调用机器人运动接口。执行时会开盖、发射激光、摆动扫描。由本程序独占相机，不同时运行APP预览、其他采集程序或第二个Demo。

## 运行

```bash
cd /home/rosadmin/whc/develop_test/atweldsystemapi
source /opt/ros/humble/setup.bash
source /home/rosadmin/whc/develop_test/install/weld_interfaces/share/weld_interfaces/local_setup.bash
export PYTHONPATH="$PWD/sdk/python:${PYTHONPATH:-}"

python3 examples/python/camera/camera_scan_demo.py
```

Python中配置DDS不能代替上述ROS环境加载。本例通过本机Python SDK直接访问ROS 2，无需SSH或rosbridge。

## 配置和调用顺序

参数来自2026-11-05 15:41成功扫描日志（参数组job=7，907099个点）。本例将这些参数直接写入相机，不读取或修改数据库中的job，也不运行上层焊接任务。

配置请求使用 `/at/camera_node/config`，`LaserConfig.Request.config_str` 为JSON字符串。例如：

```json
{"command_type":"laser_configuration","laser_config":{"laser_off":true,"laser_power_level":3}}
```

|顺序|command_type|发送内容|
|---|---|---|
|1|connect|本台相机GUID，随后检查连接、设备范围|
|2|camera_configuration|曝光600、fixed、帧率200、左右增益1；左右ROI均为left=0/right=1216/top=0/bottom=1920|
|3|laser_configuration|laser_off=true，laser_power_level=3；此时先关灯|
|4|enable_swing_motor|启用电机|
|5|set_swing_scan_mode|scan_mode=1，单次扫描|
|6|set_swing_rotate_direct|rotate_direct=0|
|7|set_swing_angle_speed|angle_speed=50|
|8|set_swing_stop_time|mseconds=500|
|9|set_swing_motor_work_range|near_distance=300.0，far_distance=800.0；沿用成功记录，不猜测单位|
|10|set_swing_motor_angle|start_pos=0，end_pos=60|

工作距离设置会影响ROI。全部配置之后再读取 `get_camera_config`；成功记录中的最终左右ROI分别为0～256和960～1216，高度均为0～1920。程序校验曝光、帧率、增益、扫描模式、方向、速度、起止位置、电机使能和激光功率，并保存最终实际ROI。

随后通过 `/at/camera_node/control` 发送 `{"command_type":"start_capture"}`。扫描驱动负责自动保护盖、频闪和激光，不要求提前调用 `open_laser` 或读到 `laser_status=true`。之前验证的“关闭频闪后手动开灯”是单独观察灯光的流程，不是本扫描的前置步骤。

程序在启动前订阅 `/at/camera_node/status`，等待capture事件按1→0到达，并要求结束通知的 `point_cloud_count` 为正整数；再通过 `/at/camera_node/get_all_point_cloud` Action下载、核对分块顺序、Action终态和总点数。服务返回200本身不代表扫描完成。超时、空点云、下载缺块或点数不一致均报错。

## 扫描之后

无论成功或失败，都尽力执行：停采、关闭激光、禁用摆动电机、关闭C版手动灯、关闭保护盖，恢复运行前的频闪和自动保护盖开关。读回确认电机禁用、普通激光状态关闭、C版手动灯关闭；保护盖以关闭命令成功响应为依据，没有位置传感器回读确认。

**保留本次写入的相机和摆动参数，不恢复运行前的曝光、ROI、功率、扫描范围、速度、工作距离和停顿时间。** 工作距离和停顿时间没有对应读取命令，不能声称完整恢复。扫描驱动也可能调整帧率，结果文件分别记录启动前配置回读和采集后回读。

## 结果文件

只有扫描、下载、总点数核对和清理都通过，才生成正式结果：

```text
scan_results/本次运行时间/
  cloud.ndjson       每行一个点云块，包含序号、总块数、时间字段和points
  result.json        总点数、块数、前三个点、配置回读和文件路径
```

失败时可能留下 `cloud.ndjson.partial`，不能当作完整点云。运行目录被Git和交付打包排除。点的 `w/p/r` 是VZ生产者存放的RGB，不是欧拉角；本接口未声明可靠的坐标系和单位，不自动转换成机器人坐标。

## 范围检查与限制

- 下发前检查扫描端点0～60和速度50位于设备报告的配置范围内；端点写入后再回读。当前编码器角度与配置端点的共同零点尚未确认，旧版把299.9直接与配置上限60比较的依据不足。此次按已成功执行的固定参数复现，不将编码器读数当作运动目标，不做除10或减360换算，也不自动归零。其他独立角度示例的保守检查保持不变。
- 该流程没有共同的采集ID，开始/结束事件与点数核对仅适用于独占相机。启动超时或清理失败不会自动重启扫描，也不能声称设备状态已确认。
- 上层成功任务实际使用 `/at/sensor/camera/scanweld_capture`，在服务内部配置、采集并写production.pcd。本例复用同样的驱动配置和采集功能，通过原有Python SDK下载本机结果，不覆盖上层production.pcd，也不启动机器人任务。

## 真机验证记录

2026-11-05本机Python SDK完整运行成功，101日志中的采集时间为19:55:47～19:55:52：

- 收到912214个点，下载823个数据块，落盘后重新统计与结束通知一致。
- 进程正常退出，result.json中的status为passed。
- 启动前帧率回读200，采集后回读973；此回读不能替代实际帧率测量。
- 清理回读：电机使能false、laser_status=false、is_turn_on_strobe_laser=false；关罩命令status=200。
- 45项相机离线测试通过，包含超时、空点云、缺块/点数不符、非法扫描端点/速度和清理失败处理。

日志与小体积结果摘要保存在仓库 `evidence/camera-scan-demo-20261105/`。本次完整点云在 `scan_results/20261105-195520-158770/cloud.ndjson`。
