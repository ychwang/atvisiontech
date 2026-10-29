# 工艺分组与工艺调用流程

## 调用顺序

1. 调用 `process_class_list` 查询活动分组，或调用 `process_class_add` 创建分组并取得返回的分组行 ID。
2. 调用 `process_add` 创建工艺。`data.class_id` 必须使用活动分组行 ID，`data.job_num` 在该分组内不得重复。
3. 调用 `process_detail` 回读工艺，或调用 `process_list_by_class` 查询组内工艺。两者的查询 ID 均填写在 `Request.id`，不是 `data.id`。
4. 调用 `process_info_update` 更新完整工艺聚合。请求必须包含 `data.id`、`data.class_id`、`data.job_num` 及该工艺所需的嵌套对象；详情响应不能直接作为更新请求重放。
5. 删除普通分组前，先删除或移走其中的活动工艺。默认分组使用单独的级联软删除规则，不应作为普通清理流程使用。

`process_class_assoc_update` 仅修改已有工艺的活动分组关联，不会创建工艺。请求结构为：

```json
{"process_class_id": 28, "process_id": 114}
```

默认分组和默认工艺受保护。调用后同时检查 `status`、`message`，并通过组内工艺查询确认关联结果。

## 工艺分组接口

|接口|请求字段|返回与解析|
|---|---|---|
|`/at/data/process_class_add`|`data.name` 必填，去除首尾空白后不得为空。`class_job_num` 可省略；省略时使用新行 ID。指定时必须为正整数且在活动记录中唯一。可选 `description`、`extension`、创建/更新时间字段。禁止提交 `id`、`is_default`、`is_delete` 和未知字段。示例名称：`平角焊`。|`status=200` 时，解析 `data` JSON 并读取字符串字段 `id`。`400` 表示参数或业务拒绝，`500` 表示服务异常。|
|`/at/data/process_class_update`|`data.id` 必填且为整数；至少再提供一个可修改字段。允许 `name`、`class_job_num`、`description`、`extension`、`update_by`、`update_time`。示例环境请求：`{"id":3,"name":"平焊"}`；其他环境替换为目标分组 ID。默认分组及 `is_default/is_delete` 写入会被拒绝。|成功时 `status=200`，`data` 通常为空字符串；空 `data` 不表示失败。|
|`/at/data/process_class_list`|请求 `id`、`data` 不参与查询，可留空。|`data` 为 JSON 数组；元素至少含 `id`、`name`、`is_default`、`is_delete`，并可能包含 `class_job_num`。没有活动分组时返回空字符串，不是 JSON `[]`。|
|`/at/data/process_class_pseudo_delete`|`id` 填写非空的分组行 ID；示例环境值为 `"7"`，其他环境替换为目标分组 ID。`data` 可留空。|成功时软删除分组。普通分组仍有活动工艺时返回 `400`，`message` 为 `Process under category not deleted.`；不会自动级联删除普通分组中的工艺。|

## 工艺聚合请求

`process_add` 和 `process_info_update` 接收完整工艺聚合。写入结构使用以下字段名称：

- `process_vec[].weldBeadInfo`
- `process_vec[].arcTrackingPara`
- `process_vec[].welding_torch_posture_params`
- `process_vec[].camera_tracking_params`
- `process_vec[].laser_tracking_params.weld_type`

接口详情中的查询结构与写入结构并非无损互逆。创建或更新时应从[字段契约](field-data-contracts.md)和随附完整模板构造请求，不要直接重放 `process_detail` 响应，也不要保留其他环境中的嵌套数据库主键。

## SDK 方法

Python：`process_class_list()`、`process_class_add(payload)`、`process_class_update(payload)`、`process_class_delete(class_id)`、`process_class_assoc_update(class_id, process_id)`、`process_list_by_class(class_id)`、`process_add(payload)`、`process_update(payload)`、`process_delete(process_id)`。

C++ 提供同名方法，JSON 请求使用 `nlohmann::json`，ID 参数使用整数。SDK 将 `payload` 原样序列化到 `ATStringGeneric.Request.data`，不注入业务字段，也不自动重试写操作；响应保留 `status`、`data` 和 `message`。

完整模块程序：`examples/python/process_workflow.py`、`examples/cpp/process_workflow.cpp`。默认只输出调用结构；连接隔离 mock 时使用 `--execute --prefix /api_process_mock`。生产环境调用创建、更新或删除接口前，应使用独立名称并确认目标分组、引用关系和清理策略。

## 删除限制

普通分组必须先没有活动工艺；默认分组使用独立的级联软删除规则。删除前先查询当前归属和引用，不要把这些接口作为通用数据库清理工具。
