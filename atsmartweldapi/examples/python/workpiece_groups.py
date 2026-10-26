#!/usr/bin/env python3
"""Workpiece-group CRUD example; new IDs are read from creation responses.

Default execution is offline.  --execute is intentionally limited to the
isolated mock namespace; it never connects to a field database.
"""

import argparse
import json


def positive_decimal_id(reply):
    try:
        value = json.loads(reply.data)["id"]
        if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
            raise ValueError("id must be an ASCII decimal string")
        result = int(value)
        if result <= 0 or result > 2147483647:
            raise ValueError("id must be positive")
        return result
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"group add returned no usable data.id: {reply.data!r}"
        ) from exc


def require_clean_update(reply):
    # Current backend can map false (0) to status=200 while retaining message.
    if reply.status != 200 or reply.message:
        raise RuntimeError(
            f"workpiece_group_update is not confirmed: status={reply.status} "
            f"message={reply.message!r} raw={reply.data!r}"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--prefix", default="")
    args = parser.parse_args()
    if not args.execute:
        print(
            'Offline example commands: add data={"name":"分组-1"}; '
            'update data={"id":"6","name":"66"}; '
            "list sort_field=id sort_descending=false page=1 items=10; "
            'detail filters=[{key:id,value:"6"}]; delete id=7.'
        )
        print("Runtime uses the newly returned id, not the example IDs 6/7.")
        return 0
    if args.prefix != "/api_group_mock":
        parser.error("--execute is restricted to --prefix /api_group_mock")
    from aotai_sdk import Client

    with Client(endpoint_prefix=args.prefix) as client:
        # Keep the example names and bind the returned group ID.
        add = client.workpiece_group_add({"name": "分组-1"})
        group_id = positive_decimal_id(add)
        listing = client.workpiece_group_list(
            filters=[],
            page_number=1,
            items_per_page=10,
            sort_field="id",
            sort_descending=False,
        )
        detail = client.workpiece_group_detail(group_id)
        require_clean_update(
            client.workpiece_group_update({"id": str(group_id), "name": "66"})
        )
        client.workpiece_group_delete(group_id)
        print(
            f"created/listed/detailed/updated/deleted dynamic group id={group_id}; "
            f"list={listing.data!r}; detail={detail.data!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
