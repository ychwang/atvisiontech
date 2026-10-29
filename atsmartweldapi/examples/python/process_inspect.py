#!/usr/bin/env python3
"""Read one process aggregate and its separately returned system configuration.

The default invocation is offline.  `--connect` performs only the two current
read services: ``/at/data/process_detail`` and
``/at/data/system_config_detail_by_process``.  It prints each service's ``data``
string unchanged.  This is deliberately not a process clone/update tool:
process_detail omits configParam, retains database-owned nested IDs, and cannot
be safely sent to process_add/process_info_update without constructing the required write
object.
"""

import argparse
import json


def positive_source_id(value):
    """Reject bools, floats, zero, and negatives before constructing a client."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("--source-id must be a positive integer")
    return value


def require_json_object(raw, label):
    """Check a response is a JSON object while returning its exact raw text."""
    if not isinstance(raw, str):
        raise ValueError(f"{label} response data must be text; raw={raw!r}")
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} response data is not JSON; raw={raw!r}") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"{label} response data must be a JSON object; raw={raw!r}")
    return raw


def read_process_responses(client, source_id, service_type):
    """Read both server views once; no automatic retry or write is performed."""
    positive_source_id(source_id)
    detail = client.process_detail(source_id)
    config = client.call(
        service_type,
        "/at/data/system_config_detail_by_process",
        {"id": str(source_id), "data": ""},
    )
    return (
        require_json_object(detail.data, "process_detail"),
        require_json_object(config.data, "system_config_detail_by_process"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--connect", action="store_true", help="perform the two read-only service calls"
    )
    parser.add_argument("--source-id", type=int, help="positive existing process ID")
    parser.add_argument("--prefix", default="", help="isolated mock namespace only")
    args = parser.parse_args()

    if not args.connect:
        print(
            "Offline: use --connect --source-id ID to read two process responses; no DB write is available."
        )
        return 0
    try:
        positive_source_id(args.source_id)
    except ValueError as error:
        parser.error(str(error))

    # Delayed imports and construction keep offline/invalid CLI paths side-effect free.
    from aotai_sdk import ApiError, Client
    from weld_interfaces.srv import ATStringGeneric

    try:
        with Client(endpoint_prefix=args.prefix) as client:
            detail_raw, config_raw = read_process_responses(
                client, args.source_id, ATStringGeneric
            )
    except ApiError as error:
        print(f"process inspection failed: {error}; raw={error.raw}")
        return 3
    except ValueError as error:
        print(f"process inspection refused: {error}")
        return 3

    # Do not normalize or combine the two shapes: callers can save/review them
    # with all returned fields intact before using the dedicated data-creation workflow.
    print(f"process_detail.data={detail_raw}")
    print(f"system_config_detail_by_process.data={config_raw}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
