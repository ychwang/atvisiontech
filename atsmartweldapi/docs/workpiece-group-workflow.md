# 工件分组调用与清理流程

## 完整调用示例

下例中的 `6`、`7` 仅为示例环境的数据库行 ID。创建成功后必须解析新返回的 ID，并将其用于后续详情、更新和删除请求。

```bash
ros2 service call /at/data/workpiece_group_list weld_interfaces/srv/ATQuery \
  '{sort_field: "id", sort_descending: false, page_number: 1, items_per_page: 10}'
ros2 service call /at/data/workpiece_group_detail weld_interfaces/srv/ATQuery \
  '{filters: [{key: "id", value: "6"}]}'
ros2 service call /at/data/workpiece_group_add weld_interfaces/srv/ATStringGeneric \
  '{data: "{\"name\":\"分组-1\"}"}'
ros2 service call /at/data/workpiece_group_update weld_interfaces/srv/ATStringGeneric \
  '{data: "{\"id\":\"6\",\"name\":\"66\"}"}'
ros2 service call /at/data/workpiece_group_pseudo_delete weld_interfaces/srv/ATStringGeneric \
  '{id: "7"}'
```

新增成功时，响应 `data` 是 JSON 字符串 `{"id":"<新ID>"}`。解析字符串 ID 后，再执行详情、更新或删除操作。

## 服务与字段

|服务|类型|请求参数|返回与判断|
|---|---|---|---|
|`/at/data/workpiece_group_list`|`ATQuery`|`filters` 必须为空。`sort_field` 可为空、`id`、`create_time` 或 `update_time`。示例使用 `page_number=1`、`items_per_page=10`、`sort_field="id"`、`sort_descending=false`。|`status=200` 时，`data` 为对象；`data.data` 是数组，`data.data_size` 是匹配总数，并回显分页与排序字段。没有活动分组时返回 `data_size:0` 和 `data:[]`。|
|`/at/data/workpiece_group_detail`|`ATQuery`|`filters` 必须含字符串键值 `id`；可同时提供 `is_template`、`model_type`。不要将外部过滤键写成 `group_id`。|`data` 为对象；`id/name/description` 属于分组，`workpieces` 为关联工件的简化数组，不是完整工件详情。|
|`/at/data/workpiece_group_add`|`ATStringGeneric`|`data` 为 JSON。不得包含 `id`；`name` 必须是非空字符串且唯一。示例：`{"name":"分组-1"}`。|成功时 `status=200`，解析 `data.id` 字符串。`400/500` 时读取 `message`。|
|`/at/data/workpiece_group_update`|`ATStringGeneric`|`data` 为 JSON，包含运行时取得的分组 ID 和修改字段。示例：`{"id":"6","name":"66"}`。|必须同时满足 `status==200` 且 `message` 为空；非空 `message` 表示更新未完成，即使 `status` 为 200 也应停止后续操作。|
|`/at/data/workpiece_group_pseudo_delete`|`ATStringGeneric`|`id` 为非空字符串行 ID，`data` 可留空。|成功时在一个事务中软删除分组及相同 `group_id` 的工件模板；不是物理删除。失败或回滚信息位于 `message`。|

## SDK 与模块示例

- Python：`workpiece_group_list(...)`、`workpiece_group_detail(group_id)`、`workpiece_group_add(payload)`、`workpiece_group_update(payload)`、`workpiece_group_delete(group_id)`。
- C++：提供同名 `Client` 方法；列表和详情返回 `ATQuery` 的 `status/data/message`。
- 完整程序：`examples/python/workpiece_groups.py`、`examples/cpp/workpiece_groups.cpp`。默认只输出调用结构；使用 `--execute --prefix /api_group_mock` 连接隔离 mock。

删除会软删除关联模板。生产环境执行删除前，必须确认分组 ID、关联模板及业务影响；不要把示例 ID 直接用于其他环境。
