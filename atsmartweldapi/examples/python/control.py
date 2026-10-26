#!/usr/bin/env python3
"""Explicit task command example; UID readback is not an ownership lock.

Run `python3 control.py get_task_status` for a read-only query.  Any control
requires `--expected-uid UID`; output is the raw task_services reply.  It does
not submit, retry, or automatically sequence device actions.
"""

import argparse
import json
from aotai_sdk import Client

parser = argparse.ArgumentParser()
parser.add_argument(
    "command",
    choices=[
        "task_start",
        "task_pause",
        "task_continue",
        "task_destroy",
        "get_task_status",
        "get_current_task",
        "recover",
    ],
)
parser.add_argument("--expected-uid")
args = parser.parse_args()
queries = {"get_task_status", "get_current_task"}
if args.command not in queries and not args.expected_uid:
    parser.error("controls/recover require --expected-uid before connecting")
with Client() as client:
    if args.command not in queries:
        current = json.loads(client.task_command("get_current_task").data)
        if current.get("project", {}).get("uid") != args.expected_uid:
            raise SystemExit(
                "current project UID mismatch/unknown; no command sent, do not re-submit"
            )
    if args.command == "recover":
        print(
            "UID matches; status (not a resume/resubmit request):",
            client.task_command("get_task_status").data,
        )
    else:
        response = client.task_command(args.command)
        print(response.status, response.message, response.data)
