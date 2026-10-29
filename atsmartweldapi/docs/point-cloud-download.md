# 点云文件下载（HTTP）

APP主页面通过HTTP下载已生成的扫描点云文件，再解析并显示；不通过ROS Service、Action或rosbridge传输这个文件。相机配置、扫描控制与文件下载是不同操作，下载本身不会开始采集。

## 请求

```http
GET http://<系统主机 IP>:10001/download/world.pcd
```

|项目|填写方式与约束|
|---|---|
|协议与方法|HTTP GET；这里不是ROS服务名，也不是WebSocket消息。|
|系统主机 IP|使用当前连接的系统主机地址。`127.0.0.1`只代表下载程序所在计算机，不是固定设备地址。|
|端口|当前服务默认10001；网络映射或部署覆盖时使用实际端口，不使用APK/WPP文件服务的10011。|
|路径|APP使用`/download/world.pcd`。`world.pcd`为本流程固定文件名，不是工程ID、工艺ID或相机GUID。|
|请求体/查询参数|此请求没有JSON请求体，也不需要frequency、sequence_id、业务ID或分页参数。|
|前置条件|扫描业务已成功生成可读的点云文件，且HTTP服务可达。请求不会创建文件或自动完成扫描。|

例如，在已经确认点云可下载后，将地址替换为实际设备地址：

```bash
curl --fail --show-error --output world.pcd 'http://<系统主机 IP>:10001/download/world.pcd'
```

示例环境地址为 `http://192.168.1.101:10001/download/world.pcd`。其他环境替换系统主机 IP 和部署端口；不要使用机器人、焊机或 rosbridge 的地址。

## 响应与结果判断

|响应项|类型/含义|处理方式|
|---|---|---|
|HTTP 200|文件读取分支返回PCD附件；Content-Type为`application/octet-stream`。|APP将下载阶段判成功，随后仍必须读取并成功解析PCD；200不证明文件非空、最新或对应指定工件。|
|Content-Disposition|`attachment; filename="world.pcd"`。|文件名是附件名称，不是JSON字段。|
|响应体|PCD文件字节，通常含文本头和二进制点记录；不是JSON，也不是ATPointCloud反馈消息。|保留原始字节，以PCD解析器读取；不能直接对整个响应调用JSON.parse。|
|HTTP 404|文件不存在；JSON错误对象。|显示失败，不把错误正文保存/显示为有效点云。|
|其他非200/网络失败|APP下载Promise拒绝。|提示失败；不将已下载的部分文件当作完整PCD，不自动触发重新扫描。|

文件不存在时返回：

```json
{"error":"File not found"}
```

`error` 是字符串错误说明，没有 `status/data` 包裹。

### PCD内部结构

PCD不是JSON对象。其头部声明如何解析后面的点数据：

|头部项|说明|
|---|---|
|VERSION|PCD格式版本；按文件实际值读取。|
|FIELDS|每个点的字段名称列表，如x、y、z；以实际头部为准，不固定补出RGB或姿态。|
|SIZE / TYPE / COUNT|依次对应各字段的字节数、存储类型及元素个数。|
|WIDTH / HEIGHT / POINTS|点云组织尺寸与点总数；不能当作下载分块序号。|
|VIEWPOINT|文件中的观察位姿元数据，不能直接推断为机器人工件坐标系。|
|DATA|后续数据编码，如binary；必须使用匹配编码解析。|
|点记录|按上述字段和编码排列的点值。3D扫描导出路径写PointXYZ，至少含x/y/z；其他扫描分支保存的字段以文件头为准。|

服务端保存前可能进行降采样，文件点数不保证等于传感器原始采集点数。接口没有传递 ROS `frame_id`、业务记录 ID 或采集时间版本号；PCD 头本身也不能证明当前业务的坐标系和长度单位。

## APP接收与显示

APP使用`uni.downloadFile`，仅`statusCode === 200`时返回`tempFilePath`，该字段是APP本地临时文件路径，**不是HTTP响应JSON字段或服务端URL**。进度回调的`progress`为百分比，`totalBytesWritten`和`totalBytesExpectedToWrite`为字节数；`fileName`是APP附加的文件名。

APP-PLUS将临时路径转换为本地URL并通过XHR读取ArrayBuffer；H5通过fetch读取ArrayBuffer，再交给Three.js `PCDLoader.parse()`。当前显示实现将点云缩放0.001并绕X轴旋转负π/2；这是APP显示变换，不是此HTTP接口对所有设备承诺的单位或坐标变换规则。

APP将临时路径同时写入当前显示状态和Vuex的`camera3DStore.pcdFilePathCache`，用于“使用上次点云文件”；该流程没有调用永久保存接口。清除显示会移除并释放Three.js点对象、清空当前显示路径，但不清除上述缓存路径，也不代表删除本地临时文件或工控机PCD。缓存仅保存路径，不保证文件长期存在；临时文件失效时必须提示失败，不能把缓存路径当成永久保存的点云。

## 文件生命周期与安全边界

- `world.pcd` 由扫描处理生成，位于系统主机 `/tmp/at_archive/world.pcd`。HTTP 下载后服务端文件保留；后续扫描或重采样可能覆盖，固定文件名不提供版本化存档。
- HTTP 200、PCD解析成功和当前工件点云正确是三个不同判断。此下载接口没有工件ID关联校验、自动等待扫描完成或原子版本绑定。
- 相机还可生成归档`vz_camera_cloud.pcd`，但当前APP主流程不请求它，不作为本页推荐入口。
- **通用下载路由对非world.pcd文件会删除服务端归档文件**，不能把其他文件的GET下载视为严格只读或可重复请求。
- 部署时应单独检查 HTTP 服务可达性、文件更新时间、PCD 非空性及坐标含义；不要用接口定义代替目标环境验收。
