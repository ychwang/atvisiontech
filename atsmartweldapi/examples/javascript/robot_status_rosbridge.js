// Browser console or Node.js 22+. Set the URL supplied by your deployment.
function queryRobotStatus(url, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(url);
    const service = "/at/robot/status";
    const id = "robot-status-" + Date.now();
    let settled = false;
    const timer = setTimeout(() => finish(new Error("等待连接或响应超时")), timeoutMs);

    function finish(error, value) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      socket.onopen = null;
      socket.onmessage = null;
      if (socket.readyState < 2) socket.close();
      if (error) reject(error);
      else resolve(value);
    }

    socket.onopen = () => socket.send(JSON.stringify({
      op: "call_service",
      id,
      service,
      args: { id: "", data: "robot_status" },
      timeout: timeoutMs / 1000
    }));
    socket.onmessage = event => {
      try {
        const reply = JSON.parse(event.data);
        if (reply.id !== id) return;
        if (reply.op === "status" && reply.level === "error") {
          throw new Error(reply.msg || "rosbridge 请求错误");
        }
        if (reply.op !== "service_response" || reply.service !== service) return;
        if (reply.result !== true) {
          throw new Error("桥接调用失败：" + JSON.stringify(reply.values));
        }
        if (!reply.values || reply.values.status !== 200) {
          throw new Error("业务查询失败：" + JSON.stringify(reply.values));
        }
        const status = JSON.parse(reply.values.data);
        if (!status || typeof status !== "object" || Array.isArray(status)) {
          throw new Error("机器人状态 data 必须是 JSON 对象");
        }
        finish(null, status);
      } catch (error) {
        finish(error);
      }
    };
    socket.onerror = () => finish(new Error("WebSocket 连接失败"));
    socket.onclose = () => finish(new Error("收到响应前连接已关闭"));
  });
}

// 127.0.0.1 refers to the computer running this example, not the controller.
const bridgeUrl = "ws://127.0.0.1:9090";
queryRobotStatus(bridgeUrl).then(console.log).catch(error => console.error(error.message));
