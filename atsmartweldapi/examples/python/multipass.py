#!/usr/bin/env python3
"""Assemble the shared multi-pass JSON; --execute is deliberately guarded.

Run `python3 multipass.py [--input multipass-input.json]` to print a local
MCS_WeldTask JSON.  `--execute` additionally requires confirmed non-demo IDs,
coplanar mode and DB readback; it may submit an Action and is never default.
"""

import argparse, json, pathlib
from aotai_sdk import (
    Client,
    load_and_assemble,
    validate_execute_input,
    verify_process_order,
)

root = pathlib.Path(__file__).parents[1] / "data"
p = argparse.ArgumentParser()
p.add_argument("--input", default=str(root / "multipass-input.json"))
p.add_argument("--execute", action="store_true")
a = p.parse_args()
source = json.load(open(a.input, encoding="utf8"))
task = load_and_assemble(a.input)
print(json.dumps(task, ensure_ascii=False, indent=2))
if a.execute:
    validate_execute_input(source)
    with Client() as c:
        for seam in source["seams"]:
            detail = c.process_detail(seam["process_id"])
            # Contract input currently binds one process per seam; verify each before submit.
            verify_process_order(json.loads(detail.data), {**source, "seams": [seam]})
        h = c.submit_task(task, lambda fb: print("feedback:", fb.status_message))
        print("ROS goal accepted:", h.accepted)
        print(h.wait_result())
