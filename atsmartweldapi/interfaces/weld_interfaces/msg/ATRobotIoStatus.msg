# RobotIOState.msg
# 机器人IO状态信息

# ===================== 数字IO状态 =====================
#uint64 standard_digital_input_bits       # 标准数字输入
#uint64 standard_digital_output_bits      # 标准数字输出
uint64 tool_digital_input_bits           # 工具端数字输入
#uint64 tool_digital_output_bits         # 工具端数字输出
#uint64 configurable_digital_input_bits   # 可配置数字输入
#uint64 configurable_digital_output_bits  # 可配置数字输出
#uint64 link_digital_input_bits          # 链路数字输入
#uint64 link_digital_output_bits         # 链路数字输出

# ===================== 模拟IO状态 =====================
#float64[] standard_analog_input_values   # 标准模拟输入
#float64[] standard_analog_output_values  # 标准模拟输出
#float64[] tool_analog_input_values       # 工具端模拟输入
#float64[] tool_analog_output_values      # 工具端模拟输出
