#!/usr/bin/env python3
"""Read the project/workpiece library; never rewrite detail as an update payload."""

import argparse
import json
from aotai_sdk import Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connect", action="store_true")
    parser.add_argument("--kind", choices=["project", "workpiece"], default="project")
    parser.add_argument(
        "--id", type=int, help="existing positive ID from the library list"
    )
    parser.add_argument("--prefix", default="")
    args = parser.parse_args()
    if args.id is not None and args.id <= 0:
        parser.error("--id must be positive; no format-only ID is executable")
    if not args.connect:
        print(
            "Offline. --connect lists the library; --connect --id ID reads a detail. No write path."
        )
        return 0
    from weld_interfaces.srv import ATQuery, ATStringGeneric

    stem = "/at/data/workpiece_task" if args.kind == "project" else "/at/data/workpiece"
    with Client(endpoint_prefix=args.prefix) as client:
        if args.id is None:
            reply = client.call(
                ATQuery,
                stem + "_list",
                {
                    "filters": [],
                    "page_number": 1,
                    "items_per_page": 20,
                    "sort_field": "id",
                    "sort_descending": True,
                },
            )
        else:
            reply = client.call(
                ATStringGeneric, stem + "_detail", {"id": str(args.id), "data": ""}
            )
        try:
            payload = json.loads(reply.data)
            if not isinstance(payload, dict):
                raise ValueError("expected JSON object")
        except (ValueError, TypeError) as error:
            raise ValueError(
                f"malformed library response; raw={reply.data!r}"
            ) from error
        print(reply.data)  # Preserve original numeric/string IDs and nested arrays.
        print(
            "Read only: project.id/string and workpiece.welds/array need verified inverse mapping before update."
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f'ERROR: {error}; raw={getattr(error, "raw", None)!r}')
        raise SystemExit(2)
