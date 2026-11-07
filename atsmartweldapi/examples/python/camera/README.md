# 3D 相机 Python 示例

本目录包含 `/at/camera_node/config` 的 **68 个命令示例，每个命令一个同名 `.py` 文件**，以及已有的搜索、配置查询、采集和点云示例。所有调用都通过本机 Python SDK 和 ROS 2/DDS 完成。

## 从连接到扫描结果

完整流程见 [camera_scan_demo.py](camera_scan_demo.py) 和[运行说明](camera_scan_demo.md)：按成功扫描记录连接、设置、单次扫描、下载并核对点云、关灯关罩停机。无需命令行参数；扫描参数保留，运行前校验下发的起止位置和速度范围。真机结果见运行说明。

## 运行一个读取示例

在 `atweldsystemapi` 根目录打开终端：

```bash
source /opt/ros/humble/setup.bash
source /home/rosadmin/whc/develop_test/install/weld_interfaces/share/weld_interfaces/local_setup.bash
export PYTHONPATH="$PWD/sdk/python:${PYTHONPATH:-}"

python3 examples/python/camera/get_camera_config.py
python3 examples/python/camera/get_laser_config.py
python3 examples/python/camera/get_resolution.py
```

`weld_interfaces` 的路径按本机安装位置调整。新示例共用 [_common.py](_common.py)，在创建 `Client()` 前加载 [fastdds_client.xml](../../config/fastdds_client.xml)：系统主机已填 `192.168.1.101`，本机网卡已填 `192.168.1.252`。更换电脑时修改 XML；相机本身先前发现的地址为 `192.168.1.20`，不能把它当成 ROS 系统主机地址。

读取示例不需要命令行参数，例如 [get_camera_config.py](get_camera_config.py)：

```python
from _common import run

if __name__ == "__main__":
    run({"command_type": "get_camera_config"})
```

`run()` 发送一次请求，打印解析后的 JSON；连接失败、业务失败或残留 `error_type` 会抛出异常。不会自动重试。原有 [camera_config.py](camera_config.py) 保留完整环境设置和 SDK 调用代码，方便不使用公共辅助函数时参考。

## 观察设置前后的变化

环境加载后，分别运行：

```bash
python3 examples/python/camera/camera_configuration.py
```

帧率203→202→203已完成真机验证。脚本打印修改前、修改后和恢复值，并在 `finally` 中恢复原帧率、核对完整配置；该示例只修改参数，不开启采图。

## 搜索和连接

```bash
# 原有搜索/采集/点云脚本仍沿用终端的 DDS 环境。
export ROS_DOMAIN_ID=0 ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$PWD/examples/config/fastdds_client.xml"
unset ROS_DISCOVERY_SERVER FASTDDS_DEFAULT_PROFILES_FILE
python3 examples/python/camera/camera_search.py --search --seconds 30
```

搜索结果通过 `/at/camera_node/sensor_search_result` 发布。将设备 `guid` 填入 [connect.py](connect.py) 的 `GUID`，再执行：

```bash
python3 examples/python/camera/connect.py
python3 examples/python/camera/connect_status.py
```

`connect.py` 已填前次发现的 GUID，换设备要更新。相机已经连接时，再发另一个 GUID 不会自动切换设备。`disconnect.py` 会中断当前连接，放在本轮测试末尾执行；之后其他配置命令通常返回未连接错误。

## 配置与动作示例

每个脚本直接展示 `command_type` 和请求参数。`camera_configuration.py` 演示实际改值并恢复；其他普通设置项通常先读取当前值，再原值写回，最后回读核对；需要修改时编辑脚本中的 `request` 或 `config`。原值写回只验证这条调用路径，不证明所有取值、开关方向或硬件效果都正确。

涉及电机、激光、保护盖、外部 IO、断开连接或标定采图的脚本含 `READY = False`。检查现场条件及参数后，在该文件中改为 `True` 再运行，无需额外命令行参数。动作示例不会自动执行相反动作或恢复连接；不要用通配符一次运行整个目录。

- `camera_configuration.py`：读取原帧率，在设备报告范围内改动1帧，回读验证，再在 `finally` 中恢复原帧率并核对完整配置；打印修改前、修改后和恢复值。只写 `frame_rate`，不改变曝光模式。
- `enable_global_denoise.py` / `disable_global_denoise.py`：测试目标开关后恢复原状态并核对；同时检查 SDK 返回码 `data == 0`。
- `set_swing_stop_time.py`：填写真实 `MSECONDS`，SDK 范围为 500～32767 毫秒；此接口没有对应读取命令，须先记录原值。
- `set_swing_motor_work_range.py`：填写真实近、远距离，并记录原值和单位；此接口没有对应读取命令。
- `set_swing_end_angle_thres.py`：拒绝把有小数的回读值截断成整数后写入。
- `set_rgb_trigger_mode.py`：先启用 RGB；原模式为1时改为0，否则改为1（0=被动触发、1=主动触发）。回读验证后恢复原模式，再恢复原 RGB 使能状态；打印前后和恢复值。
- `reboot_swing.py`：200表示重启请求被接受；后续运动前应重新查询设备状态并核对动作条件。
- `set_rgb_expose.py`：写入前核对部署 SDK 支持的曝光范围和单位；脚本拒绝越界值，不自动截断。
- `rotate_swing.py`、`rotate_swing_to_start.py`、`set_swing_cur_start_pos.py`、`set_swing_cur_end_pos.py`：动作前检查当前角度及设备报告范围；读数与范围无法对应时停止发送动作，应按设备定义核对零点和单位。
- `get_calib_board_extrinsic.py`：会采图并检测标定板，需要真实标定板与匹配配置；名称含 `get` 也不是普通读取。
- `get_detected_calib_board_info.py`：需要已有检测结果；返回图像路径属于系统主机。
- `get_eye_hand_calib_matrix.py`：填写至少 5 组对应的相机外参和机器人位姿，每组 6 个数，坐标顺序和单位须匹配标定配置。空列表会在本机拒绝，不能用虚构零点提交真机。
- `format_detect_roi.py`：驱动格式化内部默认 ROI，不读取请求中的自定义 ROI；示例会前后回读核对相机 ROI。

如果写入超时或回读不一致，先停止后续测试并核对设备状态。响应 `200` 只是接口报告成功；驱动的部分底层错误不会上传，需要结合回读和实际设备状态判断。

## 用例索引

`cases.json` 是 68 条用例的目录索引，不会批量执行设备动作。完整扫描的成功结果和输出格式见[扫描说明](camera_scan_demo.md)。

旧示例已移动到本目录：`camera_search.py`、`camera_config.py`、`camera_capture.py`、`camera_cloud.py`。采集、点云脚本保留原参数用法，直接执行时默认离线；具体接入方式见[构建与运行](../../../docs/build-run.md)。

## 命令目录

| 命令示例 | 功能 | 类型 |
|---|---|---|
| [connect](connect.py) | 连接已发现的相机 | 配置 |
| [disconnect](disconnect.py) | 断开当前相机 | 配置 |
| [connect_status](connect_status.py) | 读取连接状态 | 读取 |
| [camera_configuration](camera_configuration.py) | 写入相机曝光、帧率、增益和ROI | 配置 |
| [laser_configuration](laser_configuration.py) | 写入激光开关和功率 | 激光 |
| [get_param_range](get_param_range.py) | 读取设备参数范围 | 读取 |
| [get_camera_config](get_camera_config.py) | 读取相机配置 | 读取 |
| [get_resolution](get_resolution.py) | 读取相机分辨率 | 读取 |
| [get_laser_config](get_laser_config.py) | 读取激光配置 | 读取 |
| [laser_status](laser_status.py) | 读取激光使能状态 | 读取 |
| [set_eye_hand_calib_cfg](set_eye_hand_calib_cfg.py) | 写入手眼标定配置 | 标定 |
| [get_eye_hand_calib_cfg](get_eye_hand_calib_cfg.py) | 读取手眼标定配置 | 标定 |
| [get_calib_board_extrinsic](get_calib_board_extrinsic.py) | 采图并检测标定板外参 | 标定 |
| [get_detected_calib_board_info](get_detected_calib_board_info.py) | 读取上一次标定板检测结果 | 标定 |
| [get_eye_hand_calib_matrix](get_eye_hand_calib_matrix.py) | 根据真实样本计算手眼标定矩阵 | 标定 |
| [enable_swing_motor](enable_swing_motor.py) | 启用摆动电机 | 电机/保护盖 |
| [disable_swing_motor](disable_swing_motor.py) | 禁用摆动电机 | 电机/保护盖 |
| [reboot_swing](reboot_swing.py) | 重启摆动模块 | 电机/保护盖 |
| [is_enable_swing_motor](is_enable_swing_motor.py) | 读取摆动电机使能状态 | 读取 |
| [set_swing_angle_speed](set_swing_angle_speed.py) | 写入摆动角速度 | 电机/保护盖 |
| [get_swing_angle_speed](get_swing_angle_speed.py) | 读取摆动角速度 | 读取 |
| [set_swing_motor_angle](set_swing_motor_angle.py) | 写入摆动起止位置 | 电机/保护盖 |
| [get_swing_motor_angle](get_swing_motor_angle.py) | 读取摆动起止位置 | 读取 |
| [rotate_swing](rotate_swing.py) | 旋转到指定角度 | 电机/保护盖 |
| [rotate_swing_to_start](rotate_swing_to_start.py) | 旋转到开始位置 | 电机/保护盖 |
| [set_swing_cur_start_pos](set_swing_cur_start_pos.py) | 将当前位置设为开始位置 | 电机/保护盖 |
| [set_swing_cur_end_pos](set_swing_cur_end_pos.py) | 将当前位置设为结束位置 | 电机/保护盖 |
| [set_swing_scan_mode](set_swing_scan_mode.py) | 写入摆动扫描模式 | 电机/保护盖 |
| [get_swing_scan_mode](get_swing_scan_mode.py) | 读取摆动扫描模式 | 读取 |
| [get_swing_motor_info](get_swing_motor_info.py) | 读取摆动模块信息 | 读取 |
| [get_swing_cur_angle](get_swing_cur_angle.py) | 读取当前摆动角度 | 读取 |
| [set_swing_stop_time](set_swing_stop_time.py) | 写入摆动停顿时间 | 电机/保护盖 |
| [set_swing_rotate_direct](set_swing_rotate_direct.py) | 写入摆动方向 | 电机/保护盖 |
| [get_swing_rotate_direct](get_swing_rotate_direct.py) | 读取摆动方向 | 读取 |
| [set_swing_stop_angle](set_swing_stop_angle.py) | 写入激光器停止位置 | 电机/保护盖 |
| [get_swing_stop_angle](get_swing_stop_angle.py) | 读取激光器停止位置 | 读取 |
| [set_swing_end_angle_thres](set_swing_end_angle_thres.py) | 写入扫描完成角度阈值 | 电机/保护盖 |
| [get_swing_end_angle_thres](get_swing_end_angle_thres.py) | 读取扫描完成角度阈值 | 读取 |
| [set_swing_motor_work_range](set_swing_motor_work_range.py) | 写入摆动工作距离范围 | 电机/保护盖 |
| [enable_global_denoise](enable_global_denoise.py) | 开启全局降噪 | 配置 |
| [disable_global_denoise](disable_global_denoise.py) | 关闭全局降噪 | 配置 |
| [is_enable_global_denoise](is_enable_global_denoise.py) | 读取全局降噪状态 | 读取 |
| [is_support_rgb](is_support_rgb.py) | 查询是否支持RGB相机 | 读取 |
| [enable_rgb](enable_rgb.py) | 写入RGB使能状态 | 配置 |
| [is_enable_rgb](is_enable_rgb.py) | 读取RGB使能状态 | 读取 |
| [enable_rgb_awb](enable_rgb_awb.py) | 写入RGB自动白平衡开关 | 配置 |
| [is_enable_rgb_awb](is_enable_rgb_awb.py) | 读取RGB自动白平衡状态 | 读取 |
| [enable_rgb_auto_expose](enable_rgb_auto_expose.py) | 写入RGB自动曝光开关 | 配置 |
| [is_enable_rgb_auto_expose](is_enable_rgb_auto_expose.py) | 读取RGB自动曝光状态 | 读取 |
| [enable_strobe](enable_strobe.py) | 写入频闪开关 | 激光 |
| [is_enable_strobe](is_enable_strobe.py) | 读取频闪状态 | 读取 |
| [turn_on_strobe_laser](turn_on_strobe_laser.py) | 写入频闪激光开关 | 激光 |
| [is_turn_on_strobe_laser](is_turn_on_strobe_laser.py) | 读取频闪激光状态 | 读取 |
| [enable_auto_cover_control](enable_auto_cover_control.py) | 写入保护盖自动控制开关 | 电机/保护盖 |
| [is_enable_auto_cover_control](is_enable_auto_cover_control.py) | 读取保护盖自动控制状态 | 读取 |
| [enable_io_control](enable_io_control.py) | 写入外部IO控制开关 | 配置 |
| [is_enable_io_control](is_enable_io_control.py) | 读取外部IO控制状态 | 读取 |
| [set_rgb_expose](set_rgb_expose.py) | 写入RGB曝光值 | 配置 |
| [get_rgb_expose](get_rgb_expose.py) | 读取RGB曝光值 | 读取 |
| [set_rgb_gain](set_rgb_gain.py) | 写入RGB增益 | 配置 |
| [get_rgb_gain](get_rgb_gain.py) | 读取RGB增益 | 读取 |
| [set_rgb_trigger_mode](set_rgb_trigger_mode.py) | 写入RGB触发模式 | 配置 |
| [get_rgb_trigger_mode](get_rgb_trigger_mode.py) | 读取RGB触发模式 | 读取 |
| [set_rgb_auto_expose_thres](set_rgb_auto_expose_thres.py) | 写入RGB自动曝光阈值 | 配置 |
| [get_rgb_auto_expose_thres](get_rgb_auto_expose_thres.py) | 读取RGB自动曝光阈值 | 读取 |
| [set_anti_reflect_gain_type](set_anti_reflect_gain_type.py) | 写入抗反光增益档位 | 配置 |
| [get_anti_reflect_gain_type](get_anti_reflect_gain_type.py) | 读取抗反光增益档位 | 读取 |
| [format_detect_roi](format_detect_roi.py) | 获取SDK格式化后的默认ROI | 配置 |
