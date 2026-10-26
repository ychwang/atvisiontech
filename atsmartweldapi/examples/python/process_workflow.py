#!/usr/bin/env python3
"""Process-group CRUD example; offline by default.

Execution is restricted to an isolated mock namespace. This example does not
create or update process aggregates; see docs/process-workflow.md.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "examples/data/process-report-requests.json"


def created_id(reply):
    """ATStringGeneric add replies encode database id as a decimal string."""
    try:
        value = json.loads(reply.data)["id"]
        if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
            raise ValueError("id is not an ASCII decimal string")
        parsed = int(value)
        if parsed <= 0 or parsed > 2147483647:
            raise ValueError("id is not positive")
        return parsed
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"process_class_add returned no usable data.id: {reply.data!r}"
        ) from exc


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--prefix", default="")
    args = p.parse_args()
    cards = json.loads(REPORT.read_text(encoding="utf-8"))["blocks"]
    if not args.execute:
        print("Offline: example terminal calls:")
        for card in cards[:6]:
            print(card["text"])
        print(
            "This example does not submit process_add/update requests."
        )
        return 0
    if args.prefix != "/api_process_mock":
        p.error(
            "--execute is restricted to --prefix /api_process_mock in this delivery"
        )
    from aotai_sdk import Client

    # Keep the example group name and bind the returned ID.
    with Client(endpoint_prefix=args.prefix) as client:
        add = client.process_class_add({"name": "平角焊"})
        class_id = created_id(add)
        print(f"created process_class id={class_id}")
        client.process_class_update({"id": class_id, "name": "平焊"})
        rows = json.loads(client.process_class_list().data or "[]")
        print(
            f"class rows={len(rows)}; no process_add sent"
        )
        client.process_class_delete(class_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
