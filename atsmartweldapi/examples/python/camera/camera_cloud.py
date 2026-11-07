#!/usr/bin/env python3
"""Explicit cloud download of an already acquired camera cloud.

Run `python3 camera_cloud.py` offline, or `--download --out cloud.ndjson` only
after camera acquisition is complete.  Output is per-block raw XYZWPR NDJSON;
this program never starts acquisition and a failed file is partial.
"""

import argparse
import json
from aotai_sdk import Client

parser = argparse.ArgumentParser()
parser.add_argument("--download", action="store_true")
parser.add_argument("--request", default='{"frequency":30}')
parser.add_argument("--out", default="cloud.ndjson")
args = parser.parse_args()
if not args.download:
    print(
        "Offline: pass --download to contact camera; stop acquisition first as documented."
    )
else:
    # Partial files are retained on failure for diagnosis; never treat them as complete.
    with open(args.out, "w", encoding="utf-8") as output, Client() as client:

        def sink(sequence, total, cloud):
            row = {
                "sequence_id": sequence,
                "total_blocks": total,
                "timestamp": cloud.timestamp,
                "points": [
                    {k: getattr(point, k) for k in ("x", "y", "z", "w", "p", "r")}
                    for point in cloud.points
                ],
            }
            # Preserve raw W/P/R: the VZ producer stores RGB here, not Euler angles.
            output.write(json.dumps(row, ensure_ascii=False) + "\n")

        handle = client.download_cloud(args.request, sink)
        handle.wait_result(60)
        print(
            "Cloud download complete; frame/unit metadata remains deployment-specific."
        )
