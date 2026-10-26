#!/usr/bin/env python3
"""Rename an isolated APIDOC_VERIFY_ project; offline unless --write is given.

This is a full database update, NOT PATCH or task submission. Only this test
namespace is supported. Keep other clients from editing the same project while
running: the server API has no revision/compare-and-swap parameter.
"""
import argparse
import copy
import json

PREFIX = "APIDOC_VERIFY_"
SAFE_FLAGS = ("direct_run", "loop_execution", "need_reservation", "need_digital_start")


def validate_names(expected_name, new_name):
    for name in (expected_name, new_name):
        if not isinstance(name, str) or not name.startswith(PREFIX) or len(name) <= len(PREFIX):
            raise ValueError("Only explicitly named APIDOC_VERIFY_ test projects are supported")
    if expected_name == new_name:
        raise ValueError("New name must differ from the expected current name")


def build_update(detail, project_id, expected_name, new_name):
    validate_names(expected_name, new_name)
    if type(project_id) is not int or project_id <= 0:
        raise ValueError("project_id must be a positive integer")
    project = detail["project"]
    if project.get("id") != str(project_id):
        raise ValueError("Readback project ID does not match the selected database row")
    if detail.get("task_name") != expected_name or project.get("name") != expected_name:
        raise ValueError("Readback name differs; refusing to overwrite another project")
    for flag in SAFE_FLAGS:
        if type(project.get(flag)) is not int or project[flag] != 0:
            raise ValueError("Only test definitions with integer-zero switches are supported")
    workpieces = detail["workpieces"]
    if not isinstance(workpieces, list) or not workpieces:
        raise ValueError("Full, nonempty workpieces are required; never issue a partial update")
    ids = [wp.get("id") for wp in workpieces]
    if any(type(i) is not int or i <= 0 for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Workpiece IDs must be existing, distinct positive integers")
    # Detail task_name is a response alias; update needs top-level name.
    # Only project.id changes type. Preserve every nested workpiece/node value.
    payload = {"name": new_name, "project": copy.deepcopy(project),
               "workpieces": copy.deepcopy(workpieces)}
    payload["project"].update(id=project_id, name=new_name)
    return payload


def rename_project(client, service_type, project_id, expected_name, new_name):
    validate_names(expected_name, new_name)
    if type(project_id) is not int or project_id <= 0:
        raise ValueError("project_id must be a positive integer")

    def call(suffix, request):
        endpoint = "/at/data/workpiece_task_" + suffix
        print(json.dumps({"endpoint": endpoint, "request": request}, ensure_ascii=False), flush=True)
        reply = client.call(service_type, endpoint, request, timeout=8)
        print(json.dumps({"endpoint": endpoint, "response": {
            "status": reply.status, "data": reply.data, "message": reply.message}},
            ensure_ascii=False), flush=True)
        if reply.status != 200:
            raise ValueError("Database rejected " + suffix)
        return json.loads(reply.data)

    request = {"id": str(project_id), "data": ""}
    before = call("detail", request)
    payload = build_update(before, project_id, expected_name, new_name)
    result = call("update", {"id": "", "data": json.dumps(payload, ensure_ascii=False)})
    wanted_ids = [wp["id"] for wp in payload["workpieces"]]
    if (type(result.get("project_id")) is not int or result["project_id"] != project_id
            or result.get("workpieceIds") != wanted_ids
            or any(type(i) is not int for i in result["workpieceIds"])):
        raise ValueError("Update outcome untrusted: returned IDs differ; do not retry")
    after = call("detail", request)
    build_update(after, project_id, new_name, expected_name)  # Recheck ID/flag types as well.
    expected_project = dict(payload["project"], id=str(project_id))
    if (after.get("task_name") != new_name or after.get("project") != expected_project
            or after.get("workpieces") != payload["workpieces"]):
        raise ValueError("Update outcome untrusted: mandatory readback differs; do not retry")
    return {"verified_by_readback": True, "project_id": project_id,
            "name": new_name, "workpiece_ids": wanted_ids, "task_submitted": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--expected-name", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    validate_names(args.expected_name, args.name)
    if args.project_id <= 0:
        parser.error("--project-id must be positive")
    if not args.write:
        print("OFFLINE: no ROS calls. --write performs detail → full update → detail; no task Action.")
        return 0
    from aotai_sdk import Client
    from weld_interfaces.srv import ATStringGeneric
    try:
        with Client(node_name="isolated_project_edit") as client:
            result = rename_project(client, ATStringGeneric, args.project_id,
                                    args.expected_name, args.name)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print("STOPPED: " + str(exc))
        print("No retry/rollback/delete. If update was sent, read back before deciding what to do.")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
