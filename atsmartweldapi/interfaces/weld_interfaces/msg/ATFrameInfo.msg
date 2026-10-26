# 坐标系信息消息
string name
# 0: RobotBase, 1: Tool, 2: Workpiece, 3: Seam
# 4: Waypoint, 5: TouchSensor, 6: Vision, 7: Laser
# 8: User
int32 type
string parent
float64[16] transform
bool is_system
bool is_static
string[] children
builtin_interfaces/Time last_update
