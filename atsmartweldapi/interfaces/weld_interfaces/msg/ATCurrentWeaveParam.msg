# 当前自动作业焊缝的摆焊参数快照。
# 发布方：weld_application；Topic：/at/task/current_weave_param。
# 该消息表示“当前焊缝运行时参数”，不是工艺库全局配置。

# 当前焊缝上下文，Service 更新时必须原样带回，防止旧界面覆盖新焊缝。
string task_id
string seam_id
int32 pass_id
int32 weave_seq
bool is_weave

# 完整摆焊参数；前端调整时必须整包提交，后端不从历史值补字段。
string weave_type
float64 weave_frequency
float64 motion_speed
float64 left_amplitude
float64 right_amplitude
int32 dwell_mode              # 0=停留距离，1=停留时间
float64 left_stop_distance
float64 right_stop_distance
int32 left_stop_time_ms
int32 right_stop_time_ms
int32 direction
float64 direction_angle
float64 elevation_angle
float64 up_height

# process_default：来自当前焊缝工艺默认值；runtime_updated：运行时修改已被 SDK 接受。
string source
