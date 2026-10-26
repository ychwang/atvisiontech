"""Native ROS 2 client; import has no ROS/device side effects."""

from __future__ import annotations
import json, threading, time
import math


class ApiError(RuntimeError):
    def __init__(self, message, raw=None):
        super().__init__(message)
        self.raw = raw


class CommunicationError(ApiError):
    pass


class RequestRejected(ApiError):
    pass


class ServerError(ApiError):
    pass


class ExecutionFailed(ApiError):
    pass


def _set_fields(message, values):
    if not isinstance(values, dict):
        return values
    from rosidl_runtime_py import set_message_fields

    # ROS helper casts bool("false") to True; reject that dangerous conversion.
    types = message.get_fields_and_field_types()
    for field, value in values.items():
        if types.get(field) == "boolean" and type(value) is not bool:
            raise TypeError(f"{field} requires bool, not {type(value).__name__}")
    set_message_fields(message, values)
    return message


def _raw_response(response):
    # Keep all fields, including driver result and the three pose arrays.
    return {
        name: getattr(response, name) for name in response.get_fields_and_field_types()
    }


class Subscription:
    def __init__(self, client, sub):
        self._client, self._sub = client, sub

    def release(self):
        with self._client._lock:
            if self._sub and not self._client._closed:
                self._client._node.destroy_subscription(self._sub)
            self._sub = None


class ActionHandle:
    def __init__(self, client, goal, feedback, ac, feedback_error, strict_task=False):
        (
            self._client,
            self._goal,
            self.feedback,
            self._ac,
            self._feedback_error,
            self._strict_task,
        ) = (client, goal, feedback, ac, feedback_error, strict_task)
        self._completion_validator = None
        self._feedback_complete = None

    @property
    def accepted(self):
        return self._goal.accepted

    def release(self):
        if self._ac:
            self._client._release_action(self._ac)
            self._ac = None

    def cancel(self, timeout=5):
        self._client._guard()
        return self._client._wait(self._goal.cancel_goal_async(), timeout)

    def wait_result(self, timeout=300):
        self._client._guard()
        if not self.accepted:
            self.release()
            raise RequestRejected("ROS action goal rejected")
        deadline = None if timeout is None else time.monotonic() + timeout
        wrapped = self._client._wait(self._goal.get_result_async(), timeout)
        result = wrapped.result
        message = getattr(result, "status_message", getattr(result, "message", ""))
        project_status = None
        if self._strict_task:
            try:
                payload = json.loads(message)
                if not isinstance(payload, dict) or not isinstance(
                    payload.get("project_status"), (str, int)
                ):
                    raise ValueError("project_status missing")
                project_status = str(payload["project_status"])
            except (TypeError, ValueError, json.JSONDecodeError) as e:
                self.release()
                raise ExecutionFailed(
                    "task result is not a valid project status JSON object",
                    {"status": wrapped.status, "message": message, "result": result},
                ) from e
        # DDS result and feedback are separate channels: a result can arrive first.
        # Retain the Action client until expected cloud blocks arrive or deadline expires.
        if (
            self._feedback_complete
            and wrapped.status == 4
            and getattr(result, "status", None) == 200
        ):
            while not self._feedback_complete.is_set() and not self._feedback_error[0]:
                self._client._guard()
                if deadline is not None and time.monotonic() >= deadline:
                    break
                self._feedback_complete.wait(0.005)
        self.release()
        if self._feedback_error[0]:
            raise ExecutionFailed("feedback processing failed", self._feedback_error[0])
        if hasattr(result, "status") and result.status != 200:
            raise ExecutionFailed(
                f"action business status={result.status}",
                {"result": result, "status": result.status, "message": message},
            )
        if wrapped.status != 4:
            raise ExecutionFailed(
                f"action terminal status={wrapped.status}; message={message}",
                {"status": wrapped.status, "result": result, "message": message},
            )
        if self._completion_validator:
            self._completion_validator()
        if self._strict_task and project_status != "101006":
            raise ExecutionFailed(
                f"task is not normally complete: project_status={project_status}",
                {
                    "status": wrapped.status,
                    "result": result,
                    "message": message,
                    "project_status": project_status,
                },
            )
        return result, wrapped.status, message


class AotaiClient:
    def __init__(self, endpoint_prefix="", node_name="aotai_sdk_client"):
        self.prefix = endpoint_prefix.rstrip("/")
        self._closed = False
        self._owner = threading.get_ident()
        self._lock = threading.RLock()
        self._executor_error = None
        self._actions = set()
        try:
            import rclpy
            from rclpy.context import Context
            from rclpy.executors import SingleThreadedExecutor

            self._rclpy = rclpy
            self._context = Context()
            rclpy.init(context=self._context)
            self._node = rclpy.create_node(node_name, context=self._context)
            self._executor = SingleThreadedExecutor(context=self._context)
            self._executor.add_node(self._node)
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        except Exception as e:
            raise CommunicationError(f"ROS 2 initialization failed: {e}") from e

    def _spin(self):
        while not self._closed:
            try:
                self._executor.spin_once(timeout_sec=0.05)
            except Exception as e:
                if not self._closed:
                    self._executor_error = e
                    return

    def _endpoint(self, name):
        return f'{self.prefix}/{name.lstrip("/")}' if self.prefix else name

    def _guard(self):
        if self._closed:
            raise CommunicationError("client is closed")
        if self._executor_error is not None:
            raise CommunicationError(
                f"executor failed: {self._executor_error}"
            ) from self._executor_error
        if threading.get_ident() != self._owner:
            raise RuntimeError(
                "synchronous APIs cannot run in executor callback/non-owner thread"
            )

    def _wait(self, future, timeout):
        self._guard()
        deadline = None if timeout is None else time.monotonic() + timeout
        while not future.done():
            if self._closed:
                future.cancel()
                raise CommunicationError(
                    "client closed while waiting; server state unknown"
                )
            if self._executor_error is not None:
                future.cancel()
                raise CommunicationError(
                    "executor failed while waiting", self._executor_error
                ) from self._executor_error
            if deadline is not None and time.monotonic() >= deadline:
                future.cancel()
                raise CommunicationError(
                    f"ROS request timed out after {timeout}s; server state unknown"
                )
            time.sleep(0.005)
        try:
            return future.result()
        except Exception as e:
            raise CommunicationError(f"ROS communication failed: {e}") from e

    def call(self, service_type, endpoint, request, timeout=5, allowed_statuses=(200,)):
        self._guard()
        # Validate locally before discovery/transport creation; not a communication error.
        prepared_request = (
            _set_fields(service_type.Request(), request)
            if isinstance(request, dict)
            else request
        )
        with self._lock:
            self._guard()
            cli = self._node.create_client(service_type, self._endpoint(endpoint))
        try:
            if not cli.wait_for_service(timeout_sec=timeout):
                raise CommunicationError(
                    f"service unavailable: {self._endpoint(endpoint)}"
                )
            response = self._wait(
                cli.call_async(prepared_request),
                timeout,
            )
            status = getattr(response, "status", None)
            if status is not None and status not in allowed_statuses:
                cls = ServerError if status >= 500 else RequestRejected
                raise cls(
                    f'service status={status}: {getattr(response,"message","")}',
                    _raw_response(response),
                )
            return response
        except ApiError:
            raise
        except Exception as e:
            raise CommunicationError(f"ROS service communication failed: {e}") from e
        finally:
            with self._lock:
                if not self._closed:
                    self._node.destroy_client(cli)

    def subscribe(self, message_type, topic, callback, qos=10):
        self._guard()

        def safe(msg):
            try:
                callback(msg)
            except Exception as exc:
                self._executor_error = exc

        return Subscription(
            self,
            self._node.create_subscription(
                message_type, self._endpoint(topic), safe, qos
            ),
        )

    def send_action_goal(
        self,
        action_type,
        endpoint,
        goal,
        feedback_callback=None,
        timeout=5,
        max_feedback=128,
        strict_task=False,
    ):
        self._guard()
        from rclpy.action import ActionClient

        with self._lock:
            self._guard()
            ac = ActionClient(self._node, action_type, self._endpoint(endpoint))
            self._actions.add(ac)
        err = [None]
        feedback = []
        try:
            if not ac.wait_for_server(timeout_sec=timeout):
                raise CommunicationError(
                    f"action unavailable: {self._endpoint(endpoint)}"
                )

            def cb(msg):
                try:
                    raw = msg.feedback
                    if len(feedback) < max_feedback:
                        feedback.append(raw)
                    if feedback_callback:
                        feedback_callback(raw)
                except Exception as e:
                    err[0] = e

            handle = self._wait(
                ac.send_goal_async(
                    (
                        _set_fields(action_type.Goal(), goal)
                        if isinstance(goal, dict)
                        else goal
                    ),
                    feedback_callback=cb,
                ),
                timeout,
            )
            return ActionHandle(self, handle, feedback, ac, err, strict_task)
        except Exception:
            self._release_action(ac)
            raise

    def _release_action(self, action):
        with self._lock:
            if action in self._actions:
                action.destroy()
                self._actions.remove(action)

    @staticmethod
    def _camera_response(response):
        try:
            payload = json.loads(response.message)
            if not isinstance(payload, dict) or type(payload.get("status")) is not int:
                raise ValueError("camera response requires integer status")
        except (ValueError, TypeError) as exc:
            raise ExecutionFailed(
                "malformed camera response JSON", _raw_response(response)
            ) from exc
        if payload["status"] != 200:
            error = ServerError if payload["status"] >= 500 else RequestRejected
            raise error(
                f"camera status={payload['status']}: {payload.get('message', '')}",
                {
                    "status": payload["status"],
                    "message": response.message,
                    "response": response,
                },
            )
        return response

    # Direct typed ROS 2 mappings.  These names deliberately mirror the server
    # endpoint; they neither chain commands nor retry a control request.
    def robot_init(
        self, robot_type, robot_subtype, robot_ip, local_ip, robot_scope, timeout=5
    ):
        from weld_interfaces.srv import ATRobotInit

        return self.call(
            ATRobotInit,
            "/at/robot/init_robot",
            {
                "robot_type": robot_type,
                "robot_subtype": robot_subtype,
                "robot_ip": robot_ip,
                "local_ip": local_ip,
                "robot_scope": robot_scope,
            },
            timeout,
        )

    def robot_power(self, enable, timeout=5):
        from weld_interfaces.srv import ATBool

        return self.call(ATBool, "/at/robot/power", {"enable": enable}, timeout)

    def robot_subscribe(self, timeout=5):
        from weld_interfaces.srv import ATEmpty

        return self.call(ATEmpty, "/at/robot/subscribe", {}, timeout)

    def robot_move_step(self, move_type, direction, speed, timeout=5):
        from weld_interfaces.srv import ATRobotMoveJog

        return self.call(
            ATRobotMoveJog,
            "/at/robot/move_step",
            {
                "move_type": move_type,
                "direction": direction,
                "speed": speed,
            },
            timeout,
        )

    def welder_config(self, config_id="", data=None, timeout=5):
        """Set configuration. Handler currently ignores Request.id.

        Existing ``welder_config(id, data)`` is retained; callers can use
        ``welder_config(data=payload)`` without setting the unused id.
        """
        from weld_interfaces.srv import ATStringGeneric

        if data is None:
            data, config_id = config_id, ""
        return self.call(
            ATStringGeneric,
            "/at/welder/set_welder_config",
            {"id": config_id, "data": data},
            timeout,
        )

    def welder_connect(self, weld_ip, on, timeout=5):
        from weld_interfaces.srv import ATConnect

        return self.call(
            ATConnect,
            "/at/welder/connect",
            {
                "weld_ip": weld_ip,
                "on": on,
            },
            timeout,
        )

    def welder_certify(self, data, timeout=5):
        from weld_interfaces.srv import ATString

        return self.call(ATString, "/at/welder/certify", {"data": data}, timeout)

    def welder_robot_ready(self, enable, timeout=5):
        from weld_interfaces.srv import ATBool

        return self.call(
            ATBool, "/at/welder/set_robot_ready", {"enable": enable}, timeout
        )

    def welder_current(self, value, timeout=5):
        from weld_interfaces.srv import ATFloat

        return self.call(ATFloat, "/at/welder/set_current", {"value": value}, timeout)

    def welder_voltage(self, value, timeout=5):
        from weld_interfaces.srv import ATFloat

        return self.call(ATFloat, "/at/welder/set_voltage", {"value": value}, timeout)

    def welder_synergic_mode(self, value, timeout=5):
        from weld_interfaces.srv import ATInt

        return self.call(
            ATInt, "/at/welder/set_synergic_mode", {"value": value}, timeout
        )

    def welder_enable(self, value, timeout=5):
        from weld_interfaces.srv import ATInt

        return self.call(ATInt, "/at/welder/set_enable", {"value": value}, timeout)

    def welder_welding(self, enable, timeout=5):
        from weld_interfaces.srv import ATBool

        return self.call(ATBool, "/at/welder/welding", {"enable": enable}, timeout)

    def welder_status(self, data, timeout=5):
        from weld_interfaces.srv import ATString

        return self.call(
            ATString, "/at/welder/get_welder_status", {"data": data}, timeout
        )

    def welder_data(self, timeout=5):
        """Return the raw ATStringGeneric snapshot; parse ``response.data`` only
        after checking status because the server owns its JSON schema."""
        from weld_interfaces.srv import ATStringGeneric

        return self.call(
            ATStringGeneric,
            "/at/welder/get_welder_data",
            {
                "id": "",
                "data": "",
            },
            timeout,
        )

    # verified endpoints/wire formats
    def robot_connect(self, enable, timeout=5):
        from weld_interfaces.srv import ATBool

        return self.call(ATBool, "/at/robot/connect", {"enable": enable}, timeout)

    def robot_status(self, data="robot_status", timeout=5):
        from weld_interfaces.srv import ATStringGeneric

        return self.call(
            ATStringGeneric, "/at/robot/status", {"id": "", "data": data}, timeout
        )

    def robot_pose(self, timeout=5):
        from weld_interfaces.srv import ATRobotGetPos

        response = self.call(
            ATRobotGetPos, "/at/robot/get_pos", {}, timeout, allowed_statuses=(0, 200)
        )
        for field in ("cur_pos", "joint_pos", "flan_pos"):
            values = getattr(response, field, None)
            if (
                values is None
                or len(values) != 6
                or any(
                    isinstance(v, bool)
                    or not isinstance(v, (int, float))
                    or not math.isfinite(v)
                    for v in values
                )
            ):
                raise ExecutionFailed(
                    f"robot pose field {field} must contain six finite values",
                    _raw_response(response),
                )
        return response

    def robot_stop(self, timeout=5):
        from weld_interfaces.srv import ATEmpty

        return self.call(ATEmpty, "/at/robot/move_stop", {}, timeout)

    def camera_search(self, enable, timeout=5):
        """Call the actual camera discovery switch; explicit because it may scan."""
        from weld_interfaces.srv import ATBool

        return self.call(
            ATBool,
            "/at/camera_node/search",
            {"enable": enable},
            timeout,
        )

    def camera_config(self, config_str, timeout=5):
        from weld_interfaces.srv import LaserConfig

        return self._camera_response(
            self.call(
                LaserConfig,
                "/at/camera_node/config",
                {"config_str": config_str},
                timeout,
            )
        )

    def camera_control(self, control_str, timeout=5):
        from weld_interfaces.srv import LaserControl

        return self._camera_response(
            self.call(
                LaserControl,
                "/at/camera_node/control",
                {"control_str": control_str},
                timeout,
            )
        )

    def robot_config(self, timeout=5):
        """Read server-selected robot configuration; ATRobotGetConfig has Empty request."""
        from weld_interfaces.srv import ATRobotGetConfig

        return self.call(ATRobotGetConfig, "/at/robot/get_config", {}, timeout)

    def workpiece_group_list(
        self,
        filters=None,
        page_number=1,
        items_per_page=0,
        sort_field="",
        sort_descending=False,
        timeout=5,
    ):
        from weld_interfaces.srv import ATQuery

        return self.call(
            ATQuery,
            "/at/data/workpiece_group_list",
            {
                "filters": [] if filters is None else filters,
                "page_number": page_number,
                "items_per_page": items_per_page,
                "sort_field": sort_field,
                "sort_descending": sort_descending,
            },
            timeout,
        )

    def workpiece_group_detail(self, group_id, timeout=5):
        """Read one group: its handler accepts external filter key ``id``."""
        from weld_interfaces.srv import ATQuery

        return self.call(
            ATQuery,
            "/at/data/workpiece_group_detail",
            {
                "filters": [{"key": "id", "value": str(group_id)}],
                "page_number": 0,
                "items_per_page": 0,
                "sort_field": "",
                "sort_descending": False,
            },
            timeout,
        )

    def workpiece_group_add(self, payload, timeout=5):
        return self._process_generic(
            "/at/data/workpiece_group_add", data=payload, timeout=timeout
        )

    def workpiece_group_update(self, payload, timeout=5):
        return self._process_generic(
            "/at/data/workpiece_group_update", data=payload, timeout=timeout
        )

    def workpiece_group_delete(self, group_id, timeout=5):
        return self._process_generic(
            "/at/data/workpiece_group_pseudo_delete", id=str(group_id), timeout=timeout
        )

    def current_task(self, timeout=5):
        return self.task_command("get_current_task", timeout=timeout)

    def task_command(self, command, timeout=5):
        from weld_interfaces.srv import ATStringGeneric

        return self.call(
            ATStringGeneric,
            "/at/task/task_services",
            {"id": "", "data": json.dumps({"service_name": command})},
            timeout,
        )

    def _process_generic(self, endpoint, *, id="", data="", timeout=5):
        """Direct ATStringGeneric mapping; data is JSON text or a JSON object."""
        from weld_interfaces.srv import ATStringGeneric

        if isinstance(data, (dict, list)):
            data = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        if not isinstance(id, str) or not isinstance(data, str):
            raise TypeError("id and data must be strings (or data JSON object/list)")
        return self.call(ATStringGeneric, endpoint, {"id": id, "data": data}, timeout)

    def process_class_list(self, timeout=5):
        # Current handler ignores request.data; leave both wire fields at defaults.
        return self._process_generic("/at/data/process_class_list", timeout=timeout)

    def process_class_add(self, payload, timeout=5):
        return self._process_generic(
            "/at/data/process_class_add", data=payload, timeout=timeout
        )

    def process_class_update(self, payload, timeout=5):
        return self._process_generic(
            "/at/data/process_class_update", data=payload, timeout=timeout
        )

    def process_class_delete(self, class_id, timeout=5):
        return self._process_generic(
            "/at/data/process_class_pseudo_delete", id=str(class_id), timeout=timeout
        )

    def process_class_assoc_update(self, process_class_id, process_id, timeout=5):
        return self._process_generic(
            "/at/data/process_class_assoc_update",
            data={"process_class_id": process_class_id, "process_id": process_id},
            timeout=timeout,
        )

    def process_list_by_class(self, class_id, timeout=5):
        # Handler reads Request.id, not Request.data.
        return self._process_generic(
            "/at/data/process_list_by_class", id=str(class_id), timeout=timeout
        )

    def process_add(self, payload, timeout=5):
        return self._process_generic(
            "/at/data/process_add", data=payload, timeout=timeout
        )

    def process_update(self, payload, timeout=5):
        return self._process_generic(
            "/at/data/process_info_update", data=payload, timeout=timeout
        )

    def process_delete(self, process_id, timeout=5):
        return self._process_generic(
            "/at/data/process_pseudo_delete", id=str(process_id), timeout=timeout
        )

    def process_detail(self, process_id, timeout=5):
        from weld_interfaces.srv import ATStringGeneric

        return self.call(
            ATStringGeneric,
            "/at/data/process_detail",
            {"id": str(process_id), "data": ""},
            timeout,
        )

    def download_cloud(self, request_json, sink, timeout=30):
        from weld_interfaces.action import ATAllPointCloud

        state = {"last": -1, "total": None}
        completed = threading.Event()

        def consume(f):
            if state["total"] is None:
                state["total"] = f.total_blocks
            if (
                f.total_blocks != state["total"]
                or f.sequence_id != state["last"] + 1
                or f.sequence_id >= f.total_blocks
            ):
                raise ExecutionFailed("invalid point-cloud block sequence")
            state["last"] = f.sequence_id
            sink(f.sequence_id, f.total_blocks, f.point_cloud)
            if state["last"] == state["total"] - 1:
                completed.set()

        h = self.send_action_goal(
            ATAllPointCloud,
            "/at/camera_node/get_all_point_cloud",
            {"json_data": request_json},
            consume,
            timeout,
            max_feedback=0,
        )

        def complete():
            if state["total"] is None or state["last"] != state["total"] - 1:
                raise ExecutionFailed("point-cloud stream ended before all blocks")

        h._completion_validator = complete
        h._feedback_complete = completed
        return h

    def submit_task(self, task_json, feedback_callback=None, timeout=5):
        from weld_interfaces.action import ATWeldTask

        return self.send_action_goal(
            ATWeldTask,
            "/at/task/task_action",
            {
                "json_data": (
                    task_json
                    if isinstance(task_json, str)
                    else json.dumps(
                        task_json, ensure_ascii=False, separators=(",", ":")
                    )
                )
            },
            feedback_callback,
            timeout,
            strict_task=True,
        )

    def close(self):
        if threading.current_thread() == self._thread:
            raise RuntimeError("close() cannot run in executor callback thread")
        with self._lock:
            if self._closed:
                return
            self._closed = True
        # Do not hold the resource mutex while waiting for a user callback to return.
        self._executor.shutdown()
        with self._lock:
            for action in tuple(self._actions):
                self._release_action(action)
            self._node.destroy_node()
            self._rclpy.shutdown(context=self._context)
        if threading.current_thread() != self._thread:
            self._thread.join(2)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


Client = AotaiClient
