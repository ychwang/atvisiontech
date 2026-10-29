# 焊机查询、配置与连接顺序

首次接入按以下顺序调用：**支持型号及协议 → 已保存配置/当前配置 → 下发完整配置 → 连接**。前三项为查询；后两项会改变配置或设备状态，必须由调用方显式执行。

|步骤|接口|返回/用途|
|---|---|---|
|1|`/at/data/welder_protocol`|支持型号目录；每项含type、焊接类型、量程及模式协议|
|2|`/at/data/welder_config_list`|已保存的设备实例；含地址、序列号、配置ID及当前标志|
|3|`/at/data/welder_config_current_detail`|当前数据库设备配置，量程/模式已解析|
|4|`/at/welder/set_welder_config`|保存/应用完整配置；不是查询|
|5|`/at/welder/connect`|使用与配置一致的ip:port连接|

三项查询均为Service `weld_interfaces/srv/ATStringGeneric`，请求`{"id":"","data":""}`；无请求过滤，客户端按type精确匹配。**协议ID与配置ID来自不同表，即使数字相同也不能混用。**

```bash
ros2 service call /at/data/welder_protocol weld_interfaces/srv/ATStringGeneric '{id: "", data: ""}'
ros2 service call /at/data/welder_config_list weld_interfaces/srv/ATStringGeneric '{id: "", data: ""}'
ros2 service call /at/data/welder_config_current_detail weld_interfaces/srv/ATStringGeneric '{id: "", data: ""}'
```

## 示例环境支持的型号及模式

示例环境的协议目录包含 12 种型号。协议目录表示系统具有对应的配置与模式定义，不表示这些焊机已经连接。

|协议ID|型号type|焊接类型|模式：mode_id / mode_name / bit_data|
|---|---|---|---|
|1|MAG-350PROR PLUS|0 气保焊|1 / 恒压 / [0, 0, 0]；2 / 脉冲 / [0, 0, 1]；3 / 低飞溅 / [0, 1, 1]|
|2|MAG-500PROR PLUS|0 气保焊|1 / 恒压 / [0, 0, 0]；2 / 脉冲 / [0, 0, 1]；3 / 低飞溅 / [0, 1, 1]|
|3|NBC-350RL|0 气保焊|1 / 恒压 / [0, 0, 0]；2 / 低飞溅 / [0, 1, 1]|
|4|NBC-350RL PLUS|0 气保焊|1 / 恒压 / [0, 0, 0]；2 / 低飞溅 / [0, 1, 1]|
|5|NBC-400RP PLUS|0 气保焊|1 / 恒压 / [0, 0, 0]；2 / 脉冲 / [0, 0, 1]；3 / 快速脉冲 / [1, 0, 0]；4 / 大熔深 / [0, 1, 1]|
|6|NBC-500RP PLUS|0 气保焊|1 / 恒压 / [0, 0, 0]；2 / 脉冲 / [0, 0, 1]；3 / 快速脉冲 / [1, 0, 0]；4 / 大熔深 / [0, 1, 1]|
|7|MIG-400RP PLUS|0 气保焊|1 / 恒压 / [0, 0, 0]；2 / 脉冲 / [0, 0, 1]；3 / 快速脉冲 / [1, 0, 0]；4 / 大熔深 / [0, 1, 1]|
|8|MIG-500RP PLUS|0 气保焊|1 / 恒压 / [0, 0, 0]；2 / 脉冲 / [0, 0, 1]；3 / 快速脉冲 / [1, 0, 0]；4 / 大熔深 / [0, 1, 1]|
|9|MIG-630RP PLUS|0 气保焊|1 / 恒压 / [0, 0, 0]；2 / 脉冲 / [0, 0, 1]；3 / 快速脉冲 / [1, 0, 0]；4 / 大熔深 / [0, 1, 1]|
|10|ATWLaser-1500R|1 激光焊|1 / 连续激光模式 / [0, 0, 0]；2 / 脉冲激光模式 / [0, 0, 1]；3 / 点焊激光模式 / [1, 0, 1]|
|11|ATWLaser-2000R|1 激光焊|1 / 连续激光模式 / [0, 0, 0]；2 / 脉冲激光模式 / [0, 0, 1]；3 / 点焊激光模式 / [1, 0, 1]|
|12|ATWLaser-3000R|1 激光焊|1 / 连续激光模式 / [0, 0, 0]；2 / 脉冲激光模式 / [0, 0, 1]；3 / 点焊激光模式 / [1, 0, 1]|

当前普通焊机模式写入将bit_data三元素对应到控制寄存器位4、3、2。mode_id是该型号的模式业务编号，不是统一二进制编码；例如NBC-350RL的模式2为低飞溅[0,1,1]，MAG-500PROR PLUS的模式2为脉冲[0,0,1]。设置模式时使用mode_id，不自行将mode_id转成bit_data。

## 示例环境的已保存配置与当前配置

示例环境保存 2 条配置：配置 ID 2，`MAG-500PROR PLUS`，`is_current_use=1`；配置 ID 3，`ATWLaser-1500R`，`is_current_use=0`。当前配置为 ID 2、`MAG-500PROR PLUS`、地址 `192.168.1.2:502`。

查询结果不等于自动识别实物型号。配置或连接前，应由部署方确认目标焊机型号、序列号和地址；协议记录不含设备地址或序列号，不能直接作为完整设备配置发送。

## 响应如何解析

外层先判断status：200成功；400无数据/查询失败；500异常。然后解析data字符串：

- welder_protocol：得到数组，量程为对象、supported_welding_modes_protocols为数组；每个模式含整数mode_id、字符串mode_name和整数数组bit_data。
- welder_config_list：得到数组，但量程及supported_welding_modes_protocols仍为JSON字符串，需要**二次**解析。
- welder_config_current_detail：得到单个对象，量程/模式已解析。
- `{}`表示未配置，不代表0..0或任意值；缺少必要范围不能拼出可下发的完整配置。

只读响应解析示例（protocol_reply/config_list_reply/current_reply为查询响应）：

```python
import json

def parsed(reply):
    if reply.status != 200:
        raise RuntimeError(f"query failed: {reply.status} {reply.message}")
    return json.loads(reply.data)

protocols = parsed(protocol_reply)
configs = parsed(config_list_reply)
current = parsed(current_reply)
for config in configs:
    for key, value in list(config.items()):
        if isinstance(value, str) and (key.endswith("_range") or key == "supported_welding_modes_protocols"):
            config[key] = json.loads(value)
match = [p for p in protocols if p["type"] == current["type"]]
if len(match) != 1:
    raise RuntimeError("missing or ambiguous welder protocol")
protocol = match[0]
# protocol提供型号能力/量程/模式；current提供配置ID、IP、端口及序列号。
# 此处只解析和选择，不发送配置或连接操作。
```

首次连接前应选择正确型号，结合设备实例地址/序列号补足完整配置并核对所有必要量程。配置成功后才允许使用相同ip:port连接；查询成功不表示配置已应用、认证通过或设备已连接。
