int16 synergic_mode			                # 一元化模式 0:关闭， 1：开启 
int16 enable				                # 使能状态 0:关闭， 1：开启 
int16 weld_mode				                # 焊接模式id
float64 set_voltage_arc_length		        # 设定电压值或弧长值
float64 set_current			                # 设定电流(A)
float64 real_time_voltage		            # 实际电压(V)
float64 real_time_current		            # 实际电流(A)
float64 real_time_wire_speed		        # 实际送丝速度(气保焊)
int64 timestamp      			            # 时间戳(ms)
int16 welding_process_type                  # 0:MIG/MAG ,1:LASER
float64 set_wire_feed_speed		            # 设定送丝速度(m/min)（激光焊）
float64 set_power			                # 设定功率(W)（激光焊）
float64 real_time_wire_feed_speed		    # 实际送丝速度(m/min)（激光焊）
float64 real_time_power		                # 实际功率(W)（激光焊）
int16 push_wire_status                      # 送丝状态 (0:关闭, 1:开启)
int16 pull_wire_status                      # 退丝状态 (0:关闭, 1:开启)
int16 gas_status                            # 送气状态 (0:关闭, 1:开启)
int16 welding_status                        # 是否焊接中状态 (0:关闭, 1:开启)
