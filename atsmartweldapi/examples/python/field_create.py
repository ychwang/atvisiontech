#!/usr/bin/env python3
"""Create four isolated field-validation records; default mode is offline.

The online path only creates a process group, an ordinary process, a
multi-pass process, and a project definition.  It never submits or starts a
task.  A timeout after a create request leaves the database outcome unknown,
so the program stops without retrying or cleaning up.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
from pathlib import Path


DEFAULT_INPUT = Path(__file__).resolve().parents[1] / "data/field-create-templates.json"
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}\Z", re.ASCII)
SAFE_SWITCHES = (
    "direct_run",
    "loop_execution",
    "need_reservation",
    "need_digital_start",
)


class ValidationError(ValueError):
    """The local template or a server reply violates the documented contract."""


def load_template(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValidationError("template root must be a JSON object")
    for key in ("reference_environment", "group", "ordinary_process", "multipass_process", "project"):
        if not isinstance(payload.get(key), dict):
            raise ValidationError(f"template.{key} must be a JSON object")
    return payload


def validate_run_id(run_id: str) -> None:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValidationError(
            "--run-id must be 1..48 ASCII letters/digits/underscore/hyphen and start alphanumeric"
        )


def _require_safe_project(project_payload: dict) -> None:
    project = project_payload.get("project")
    workpieces = project_payload.get("workpieces")
    if not isinstance(project, dict):
        raise ValidationError("template.project.project must be an object")
    if not isinstance(workpieces, list) or len(workpieces) != 2:
        raise ValidationError("template.project.workpieces must contain ordinary and multipass entries")
    for key in SAFE_SWITCHES:
        value = project.get(key)
        if type(value) is not int or value != 0:  # bool is intentionally rejected
            raise ValidationError(f"project.{key} must be integer 0")
    for index, workpiece in enumerate(workpieces, 1):
        if not isinstance(workpiece, dict) or not isinstance(workpiece.get("nodes"), list):
            raise ValidationError(f"workpieces[{index - 1}] must have a nodes array")
        if not workpiece["nodes"]:
            raise ValidationError(f"workpieces[{index - 1}].nodes must not be empty")


def prepare_payloads(template: dict, run_id: str, ids: tuple[int, int, int] | None = None) -> dict:
    """Copy the field template, isolate names/uids, and bind IDs when known."""
    validate_run_id(run_id)
    data = copy.deepcopy(template)
    _require_safe_project(data["project"])
    stem = f"APIDOC_VERIFY_{run_id}"
    data["group"]["name"] = stem + "_group"
    data["ordinary_process"]["name"] = stem + "_ordinary"
    data["multipass_process"]["name"] = stem + "_multipass"
    project_payload = data["project"]
    project_payload["name"] = stem + "_project"
    project_payload["project"]["name"] = stem + "_project"
    project_payload["project"]["uid"] = stem + "_project"

    # The saved reference project is not a planned task. For this single-line
    # multi-pass example, future NEW project payloads need explicit coplanar mode.
    global_source = data["ordinary_process"]["global_process"]
    global_keys = ("enable_offset_correction", "target_accuracy_threshold", "smoothing_parameters", "planning_parameters", "enable_free_pose", "enable_input_safe_point")
    future_global = {key: copy.deepcopy(global_source[key]) for key in global_keys}
    for key in ("enable_offset_correction", "enable_free_pose", "enable_input_safe_point"):
        if type(future_global[key]) is not int:
            raise ValidationError("global process flag must be integer: " + key)
    threshold = future_global["target_accuracy_threshold"]
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or threshold <= 0:
        raise ValidationError("global accuracy threshold must be finite and positive")
    for key in ("smoothing_parameters", "planning_parameters"):
        if not isinstance(future_global[key], str):
            raise ValidationError("global planning parameters must be strings")
    future_global["coplanarity_check_mode"] = 1
    project_payload["workpieces"][1]["global_process"] = future_global

    process_ids = None if ids is None else ids[1:]
    node_number = 0
    for index, workpiece in enumerate(project_payload["workpieces"], 1):
        workpiece["name"] = f"{stem}_workpiece{index}"
        workpiece["uid"] = f"{stem}_workpiece{index}"
        if process_ids is not None:
            workpiece["process_class_id"] = ids[0]
            workpiece["weld_process_id"] = process_ids[index - 1]
        for node in workpiece["nodes"]:
            if not isinstance(node, dict):
                raise ValidationError("every workpiece node must be an object")
            node_number += 1
            node["name"] = f"{stem}_seam{node_number}"
            node["uid"] = f"{stem}_seam{node_number}"
            if process_ids is not None:
                node["process_class_id"] = ids[0]
                node["weld_process_id"] = process_ids[index - 1]

    if ids is not None:
        group_id, ordinary_id, multipass_id = ids
        if any(type(value) is not int or value <= 0 for value in ids):
            raise ValidationError("created IDs must be positive integers")
        data["ordinary_process"]["class_id"] = str(group_id)
        data["multipass_process"]["class_id"] = str(group_id)
        # Keep the explicit assignments visible: these are the only process IDs
        # allowed in the two ordered workpiece branches.
        project_payload["workpieces"][0]["weld_process_id"] = ordinary_id
        project_payload["workpieces"][1]["weld_process_id"] = multipass_id
    return data


def _reply_dict(reply) -> dict:
    return {
        key: getattr(reply, key)
        for key in ("status", "data", "message", "result")
        if hasattr(reply, key)
    }


def _print_exchange(step: str, endpoint: str, request: dict, reply) -> None:
    print(json.dumps({"step": step, "endpoint": endpoint, "request": request}, ensure_ascii=False, indent=2))
    print(json.dumps({"step": step, "response": _reply_dict(reply)}, ensure_ascii=False, indent=2, default=str))


def _accepted(reply, step: str) -> None:
    if getattr(reply, "status", None) != 200:
        raise ValidationError(f"{step} rejected: raw={_reply_dict(reply)!r}")


def _decimal_data_id(reply, step: str) -> int:
    _accepted(reply, step)
    try:
        value = json.loads(reply.data)["id"]
        if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
            raise ValueError("id is not an ASCII decimal string")
        parsed = int(value)
        if parsed <= 0:
            raise ValueError("id is not positive")
        return parsed
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{step} returned invalid data.id: {getattr(reply, 'data', None)!r}") from exc


def _project_ids(reply) -> tuple[int, list[int]]:
    _accepted(reply, "project_add")
    try:
        data = json.loads(reply.data)
        project_id = data["project_id"]
        workpiece_ids = data["workpieceIds"]
        if type(project_id) is not int or project_id <= 0:
            raise ValueError("project_id must be a positive integer")
        if not isinstance(workpiece_ids, list) or len(workpiece_ids) != 2:
            raise ValueError("workpieceIds must contain two ordered entries")
        if any(type(value) is not int or value <= 0 for value in workpiece_ids):
            raise ValueError("workpieceIds entries must be positive integers")
        return project_id, workpiece_ids
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ValidationError(f"project_add returned invalid data: {getattr(reply, 'data', None)!r}") from exc


def _create_records(template: dict, run_id: str, client, service_type, partial: dict) -> dict:
    """Four creates plus mandatory readback; 200+IDs alone do not prove commit."""
    prepared = prepare_payloads(template, run_id)

    group_request = prepared["group"]
    print(json.dumps({"step": "group_add", "endpoint": "/at/data/process_class_add", "request": group_request}, ensure_ascii=False, indent=2))
    group_reply = client.process_class_add(group_request)
    print(json.dumps({"step": "group_add", "response": _reply_dict(group_reply)}, ensure_ascii=False, indent=2, default=str))
    group_id = _decimal_data_id(group_reply, "group_add")
    partial["group_id"] = group_id

    ordinary_request = prepared["ordinary_process"]
    ordinary_request["class_id"] = str(group_id)
    print(json.dumps({"step": "ordinary_process_add", "endpoint": "/at/data/process_add", "request": ordinary_request}, ensure_ascii=False, indent=2))
    ordinary_reply = client.process_add(ordinary_request)
    print(json.dumps({"step": "ordinary_process_add", "response": _reply_dict(ordinary_reply)}, ensure_ascii=False, indent=2, default=str))
    ordinary_id = _decimal_data_id(ordinary_reply, "ordinary_process_add")
    partial["ordinary_id"] = ordinary_id

    multipass_request = prepared["multipass_process"]
    multipass_request["class_id"] = str(group_id)
    print(json.dumps({"step": "multipass_process_add", "endpoint": "/at/data/process_add", "request": multipass_request}, ensure_ascii=False, indent=2))
    multipass_reply = client.process_add(multipass_request)
    print(json.dumps({"step": "multipass_process_add", "response": _reply_dict(multipass_reply)}, ensure_ascii=False, indent=2, default=str))
    multipass_id = _decimal_data_id(multipass_reply, "multipass_process_add")
    partial["multipass_id"] = multipass_id

    bound = prepare_payloads(template, run_id, (group_id, ordinary_id, multipass_id))
    project_request = {"id": "", "data": json.dumps(bound["project"], ensure_ascii=False, separators=(",", ":"))}
    print(json.dumps({"step": "project_add", "endpoint": "/at/data/workpiece_task_add", "request": project_request}, ensure_ascii=False, indent=2))
    project_reply = client.call(service_type, "/at/data/workpiece_task_add", project_request, timeout=5)
    print(json.dumps({"step": "project_add", "response": _reply_dict(project_reply)}, ensure_ascii=False, indent=2, default=str))
    project_id, workpiece_ids = _project_ids(project_reply)
    partial.update(project_id_unverified=project_id, workpiece_ids_unverified=workpiece_ids)
    detail_request = {"id": str(project_id), "data": ""}
    print(json.dumps({"step": "project_readback", "endpoint": "/at/data/workpiece_task_detail", "request": detail_request}, ensure_ascii=False))
    detail_reply = client.call(service_type, "/at/data/workpiece_task_detail", detail_request, timeout=5)
    _print_exchange("project_readback", "/at/data/workpiece_task_detail", detail_request, detail_reply)
    verify_project_readback(detail_reply, bound["project"], project_id, workpiece_ids)
    result = {
        "verified_by_readback": True,
        "group_id": group_id,
        "ordinary_process_id": ordinary_id,
        "multipass_process_id": multipass_id,
        "project_id": project_id,
        "workpiece_ids_in_request_order": workpiece_ids,
        "task_submitted": False,
        "task_started": False,
    }
    print(json.dumps({"created": result}, ensure_ascii=False, indent=2))
    print("禁止现场提交：本示例到工程数据库创建即停止，不提供任务 Action、启动或控制路径。")
    return result


def verify_project_readback(reply, expected: dict, project_id: int, workpiece_ids: list[int]) -> None:
    """Reject a plausible 200 reply if the aggregate was rolled back or mismatched."""
    _accepted(reply, "project_readback")
    try:
        data = json.loads(reply.data)
        project = data["project"]
        if project["id"] != str(project_id) or data["task_name"] != expected["name"]:
            raise ValueError("project identity/name mismatch")
        for key in ("name", "uid", *SAFE_SWITCHES):
            if type(project[key]) is not type(expected["project"][key]) or project[key] != expected["project"][key]:
                raise ValueError("project strategy mismatch: " + key)
        workpieces = data["workpieces"]
        if len(workpieces) != len(workpiece_ids):
            raise ValueError("workpiece count mismatch")
        for index, (actual, wanted) in enumerate(zip(workpieces, expected["workpieces"])):
            if type(actual["id"]) is not int or actual["id"] != workpiece_ids[index]:
                raise ValueError("workpiece ID order mismatch")
            for key in ("name", "uid", "weld_process_id", "process_class_id"):
                if type(actual[key]) is not type(wanted[key]) or actual[key] != wanted[key]:
                    raise ValueError("workpiece binding mismatch: " + key)
            if actual.get("global_process") != wanted.get("global_process"):
                raise ValueError("global process readback mismatch")
            if len(actual["nodes"]) != len(wanted["nodes"]):
                raise ValueError("node count mismatch")
            for node, wanted_node in zip(actual["nodes"], wanted["nodes"]):
                for key in ("name", "uid", "weld_process_id", "process_class_id"):
                    if type(node[key]) is not type(wanted_node[key]) or node[key] != wanted_node[key]:
                        raise ValueError("node binding mismatch: " + key)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValidationError("Project outcome untrusted: mandatory readback mismatch; do not retry or submit") from exc


def create_records(template: dict, run_id: str, client, service_type) -> dict:
    partial = {}
    try:
        return _create_records(template, run_id, client, service_type, partial)
    except Exception:
        print(json.dumps({"partial_creation": partial, "remaining_outcome": "untrusted or unknown; inspect read-only", "retry": False, "cleanup": False}, ensure_ascii=False))
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--create", action="store_true", help="perform the four database create calls")
    parser.add_argument("--run-id", help="required isolated ASCII nonce for --create")
    parser.add_argument("--prefix", default="", help="test/mocking namespace only; leave empty on the field controller")
    args = parser.parse_args(argv)
    template = load_template(args.input)
    if not args.create:
        print("OFFLINE PLAN: no ROS call is made. Full confirmed field template follows:")
        print(json.dumps(template, ensure_ascii=False, indent=2))
        print(
            "Online mode performs four database creates, verifies the project by a read-only query, then stops; "
            "even with direct_run=0 this example never sends a task Action or start/control call."
        )
        return 0
    if not args.run_id:
        parser.error("--create requires --run-id")
    validate_run_id(args.run_id)
    if args.prefix and args.prefix != "/api_field_create_mock":
        parser.error("--prefix is reserved for the isolated /api_field_create_mock namespace")
    from aotai_sdk import Client
    from weld_interfaces.srv import ATStringGeneric

    try:
        with Client(endpoint_prefix=args.prefix) as client:
            create_records(template, args.run_id, client, ATStringGeneric)
        return 0
    except Exception as exc:
        text = str(exc).lower()
        if "timed out" in text or "timeout" in text or "state unknown" in text:
            print(f"OUTCOME UNKNOWN: create request may have reached the server; stopped without retry/cleanup: {exc}")
        else:
            print(f"CREATE STOPPED: no retry/cleanup is attempted: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
