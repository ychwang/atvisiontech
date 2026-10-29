"""Local MCS task assembly. This is not a server API or a trajectory planner."""

import json, math
from copy import deepcopy


class ValidationError(ValueError):
    pass


def _finite(value, field):
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValidationError(f"{field} must be finite")


def _keys(obj, allowed, where):
    if not isinstance(obj, dict):
        raise ValidationError(f"{where} must be an object")
    missing = set(allowed) - set(obj)
    if missing:
        raise ValidationError(f"{where}: missing fields: {sorted(missing)}")
    unknown = set(obj) - set(allowed)
    if unknown:
        raise ValidationError(f"{where}: unsupported fields: {sorted(unknown)}")


def _global_process(value):
    """Validate the MCS workpiece global_process subset emitted by this mapper."""
    _keys(
        value,
        (
            "coplanarity_check_mode",
            "enable_offset_correction",
            "target_accuracy_threshold",
            "smoothing_parameters",
            "planning_parameters",
            "enable_free_pose",
            "enable_input_safe_point",
        ),
        "workpiece.global_process",
    )
    for key in (
        "coplanarity_check_mode",
        "enable_offset_correction",
        "enable_free_pose",
        "enable_input_safe_point",
    ):
        if type(value.get(key)) is not int or value[key] not in (0, 1):
            raise ValidationError(f"{key} must be 0 or 1")
    _finite(value.get("target_accuracy_threshold"), "target_accuracy_threshold")
    if value["target_accuracy_threshold"] < 0:
        raise ValidationError("target_accuracy_threshold must be non-negative")
    for key in ("smoothing_parameters", "planning_parameters"):
        if not isinstance(value.get(key), str):
            raise ValidationError(f"{key} must be text")
    return dict(value)


def _point(p, uid):
    _keys(p, ("x", "y", "z", "w", "p", "r"), "base_path point")
    if set(p) != {"x", "y", "z", "w", "p", "r"}:
        raise ValidationError("base_path point requires x,y,z,w,p,r")
    for k, v in p.items():
        _finite(v, k)
    return dict(p, uid=uid, valid=True)


def assemble_task(source):
    """Convert the narrow shared input schema to the current MCS JSON serializer shape."""
    d = deepcopy(source)
    _keys(
        d,
        (
            "schema_version",
            "demonstration_only",
            "coordinate_contract",
            "project",
            "workpiece",
            "seams",
        ),
        "input",
    )
    if (
        not isinstance(d.get("schema_version"), int)
        or isinstance(d.get("schema_version"), bool)
        or d.get("schema_version") != 1
    ):
        raise ValidationError("schema_version must be 1")
    cc = d.get("coordinate_contract", {})
    _keys(
        cc,
        ("frame", "position_unit", "orientation_convention", "angle_unit", "confirmed"),
        "coordinate_contract",
    )
    if not all(
        k in cc
        for k in (
            "frame",
            "position_unit",
            "orientation_convention",
            "angle_unit",
            "confirmed",
        )
    ) or not isinstance(cc.get("confirmed"), bool):
        raise ValidationError("incomplete or invalid coordinate_contract")
    # This mapper emits raw point x/y/z/w/p/r without conversion.  Its narrow
    # schema is therefore fixed rather than merely marked `confirmed`.
    expected_coordinate_contract = {
        "frame": "RobotBase",
        "position_unit": "mm",
        "orientation_convention": "XYZ Euler: w,p,r",
        "angle_unit": "degree",
    }
    for field, expected in expected_coordinate_contract.items():
        if cc.get(field) != expected:
            raise ValidationError(
                f"coordinate_contract.{field} must be {expected!r} for this mapper"
            )
    project = d.get("project", {})
    workpiece = d.get("workpiece", {})
    seams = d.get("seams")
    _keys(project, ("uid", "name", "system_config_id"), "project")
    _keys(
        workpiece,
        ("uid", "name", "robot_tcp_id", "global_process"),
        "workpiece",
    )
    global_process = _global_process(workpiece.get("global_process"))
    if not isinstance(d.get("demonstration_only"), bool):
        raise ValidationError("demonstration_only must be boolean")
    for container, key in ((project, "system_config_id"), (workpiece, "robot_tcp_id")):
        value = container.get(key)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= value <= 2147483647
        ):
            raise ValidationError(f"{key} must be a non-negative integer")
    if (
        not isinstance(seams, list)
        or not seams
        or not all(
            isinstance(x.get("uid"), str)
            and x["uid"].strip()
            and isinstance(x.get("name"), str)
            and x["name"].strip()
            for x in (project, workpiece)
        )
    ):
        raise ValidationError("project/workpiece uid/name and seams are required")
    seen = set()
    nodes = []
    for s in seams:
        _keys(s, ("uid", "name", "process_id", "base_path", "passes"), "seam")
        if (
            not isinstance(s.get("uid"), str)
            or not s["uid"].strip()
            or s["uid"] in seen
            or not isinstance(s.get("name"), str)
            or not s["name"].strip()
        ):
            raise ValidationError("seam uid/name must be nonempty; uid unique")
        seen.add(s["uid"])
        if (
            not isinstance(s.get("process_id"), int)
            or isinstance(s.get("process_id"), bool)
            or not 0 <= s["process_id"] <= 2147483647
        ):
            raise ValidationError("process_id must be a non-negative integer")
        path = s.get("base_path", [])
        if not isinstance(path, list) or len(path) != 2:
            raise ValidationError(
                "only line node_type=0 with exactly two base_path points is supported"
            )
        path = [_point(x, f"{s['uid']}-point-{i+1}") for i, x in enumerate(path)]
        passes = s.get("passes", [])
        if not isinstance(passes, list) or not passes:
            raise ValidationError("passes must not be empty")
        # Current parseLineSeam only applies line multi-pass offsets in mode 1.
        # Mode 0 calls coplanarityFreeLine (no offset calculation); mode 2 is
        # not handled by this narrow single-line mapper.
        if len(passes) > 1 and global_process["coplanarity_check_mode"] != 1:
            raise ValidationError(
                "multi-pass line input requires coplanarity_check_mode=1 (coplanar)"
            )
        params = []
        for n, p in enumerate(passes, 1):
            _keys(
                p,
                (
                    "index",
                    "layer",
                    "offset_horizontal_mm",
                    "offset_vertical_mm",
                    "offset_start_mm",
                    "offset_end_mm",
                    "direction_horizontal",
                    "direction_vertical",
                    "direction_forward",
                    "direction_end",
                    "weld_layer",
                ),
                "pass",
            )
            if (
                not isinstance(p.get("index"), int)
                or p.get("index") != n
                or isinstance(p.get("index"), bool)
                or not isinstance(p.get("layer"), int)
                or isinstance(p.get("layer"), bool)
                or not 1 <= p["layer"] <= 2147483647
            ):
                raise ValidationError("passes must be index 1..N with layer >= 1")
            for k in (
                "offset_horizontal_mm",
                "offset_vertical_mm",
                "offset_start_mm",
                "offset_end_mm",
            ):
                _finite(p.get(k), k)
            for k in (
                "direction_horizontal",
                "direction_vertical",
                "direction_forward",
                "direction_end",
                "weld_layer",
            ):
                if not isinstance(p.get(k), int) or isinstance(p.get(k), bool):
                    raise ValidationError(f"{k} must be integer")
                if not -1 <= p[k] <= 2147483647:
                    raise ValidationError(f"{k} is outside integer range")
                if k.startswith("direction_") and p[k] not in (0, 1):
                    raise ValidationError(f"{k} must be 0 or 1")
            params.append(
                {
                    "multi_index": n,
                    "multi_offset_horizontal": p["offset_horizontal_mm"],
                    "multi_offset_vertical": p["offset_vertical_mm"],
                    "multi_offset_start": p["offset_start_mm"],
                    "multi_offset_end": p["offset_end_mm"],
                    "multi_dir_horizontal": p["direction_horizontal"],
                    "multi_dir_vertical": p["direction_vertical"],
                    "multi_dir_forward": p["direction_forward"],
                    "multi_offset_dir_end": p["direction_end"],
                    "multi_offset_mode": 0,
                    "multi_offset_x": 0.0,
                    "layer_index": p["layer"],
                    "weld_layer": p["weld_layer"],
                }
            )
        nodes.append(
            {
                "uid": s["uid"],
                "name": s.get("name", ""),
                "node_type": 0,
                "path": path,
                "weld_process_id": s.get("process_id", 0),
                "is_multi": True,
                "multi_layer_num": max(x["layer_index"] for x in params),
                "multi_pass_num": len(params),
                "multi_pass_params": params,
            }
        )
    return {
        "project": {
            "id": 0,
            "name": project.get("name", ""),
            "uid": project["uid"],
            "loop_execution": 0,
            "need_digital_start": 0,
            "direct_run": 0,
            "need_reservation": 0,
            "system_config_id": project.get("system_config_id", 0),
            "execution_mode": 1,
            "task_source": 0,
        },
        "workpieces": [
            {
                "id": 0,
                "workpiece_id": 0,
                "uid": workpiece["uid"],
                "name": workpiece.get("name", ""),
                "laser_task_type": 0,
                "scanning_welding": 0,
                "scanning_mode": 0,
                "nodes": nodes,
                "weld_process_id": 0,
                "global_process": global_process,
                "workpiece_type": 0,
                "robot_tcp_id": workpiece.get("robot_tcp_id", 0),
                "workpiece_db_id": 0,
                "tracker_type": 2,
            }
        ],
    }


def load_and_assemble(path):
    with open(path, encoding="utf-8") as f:
        return assemble_task(json.load(f))


def validate_execute_input(source):
    task = assemble_task(source)
    if source.get("demonstration_only", True):
        raise ValidationError("demonstration_only must be false for execute")
    cc = source.get("coordinate_contract", {})
    if not cc.get("confirmed"):
        raise ValidationError("coordinate_contract.confirmed must be true for execute")
    if (
        source.get("project", {}).get("system_config_id", 0) <= 0
        or source.get("workpiece", {}).get("robot_tcp_id", 0) <= 0
    ):
        raise ValidationError("positive system_config_id and robot_tcp_id required")
    global_process = source.get("workpiece", {}).get("global_process", {})
    if (
        any(len(seam.get("passes", [])) > 1 for seam in source.get("seams", []))
        and global_process.get("coplanarity_check_mode") != 1
    ):
        raise ValidationError("multi-pass execution requires coplanarity_check_mode=1")
    for seam in source.get("seams", []):
        if seam.get("process_id", 0) <= 0:
            raise ValidationError("positive process_id required")
    return task


def verify_process_order(detail, source):
    """Fail closed: current DB query has no ORDER BY; do not locally reorder."""
    assemble_task(source)
    if not isinstance(detail, dict):
        raise ValidationError("process detail must be an object")
    pv = detail.get("process_vec")
    mp = detail.get("multi_pass_params")

    if len(source.get("seams", [])) != 1:
        raise ValidationError("verify one seam/process detail at a time")
    expected = source["seams"][0]["passes"]
    if (
        not isinstance(pv, list)
        or not isinstance(mp, list)
        or len(pv) != len(expected)
        or len(mp) != len(expected)
    ):
        raise ValidationError(
            "process detail length missing or mismatched; execution order unproven"
        )
    bead_count_by_layer = {}
    for i, p in enumerate(expected):
        a, b = pv[i], mp[i]
        layer = p["layer"]
        bead_count_by_layer[layer] = bead_count_by_layer.get(layer, 0) + 1
        expected_bead_num = bead_count_by_layer[layer]
        if not isinstance(a, dict) or not isinstance(b, dict):
            raise ValidationError("process detail entries must be objects")
        if not all(
            type(a.get(k)) is int
            for k in ("weld_bead_process_order", "layer_num", "bead_num")
        ) or not all(type(b.get(k)) is int for k in ("multi_index", "layer_index")):
            raise ValidationError(
                "process order/layer/bead identifiers must be integers"
            )
        if (
            a.get("weld_bead_process_order") != p["index"]
            or a.get("layer_num") != p["layer"]
            or a.get("bead_num") != expected_bead_num
            or b.get("multi_index") != p["index"]
            or b.get("layer_index") != p["layer"]
        ):
            raise ValidationError(
                f"process order mismatch at index {i}; current code does not prove execution order"
            )
    return True
