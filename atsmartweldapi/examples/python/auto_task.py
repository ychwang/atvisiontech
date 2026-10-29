#!/usr/bin/env python3
"""Native Python SDK automatic-task CLI; no network access without a subcommand."""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SAFE_FLAGS = ('direct_run', 'loop_execution', 'need_reservation', 'need_digital_start')
WARNING = ('超时/断线/Ctrl+C 不会停止服务端任务；状态可能未知。不要重复下发，'
           '先查询状态并现场检查。关闭 SDK 或 Action cancel 都不等于设备停止。')


def reject_constant(value):
    raise ValueError('JSON 不允许非有限数值：' + value)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('JSON 字段重复：' + key)
        result[key] = value
    return result


def parse_json(text):
    value = json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_object)
    # Also rejects exponent overflow (e.g. 1e999), not just NaN/Infinity literals.
    json.dumps(value, allow_nan=False)
    return value


def validate_task(task, expected_uid=None, live=False):
    """Structural checks only, NOT trajectory/process/safety certification."""
    if not isinstance(task, dict):
        raise ValueError('任务必须是包含 project 和 workpieces 的 JSON 对象')
    project, workpieces = task.get('project'), task.get('workpieces')
    if not isinstance(project, dict) or not isinstance(workpieces, list) or not workpieces:
        raise ValueError('必须提供 project 对象和非空 workpieces 数组，不能只提供工程 ID')
    uid = project.get('uid')
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError('project.uid 必须是非空字符串')
    if expected_uid is not None and uid != expected_uid:
        raise ValueError('project.uid 与 --expected-uid 不一致，拒绝操作')
    for field in SAFE_FLAGS:
        if type(project.get(field)) is not int or project[field] != 0:
            raise ValueError(f'本脚本要求 project.{field} 为整数 0，不自动修改你的输入')
    ids = []
    for index, workpiece in enumerate(workpieces):
        if not isinstance(workpiece, dict):
            raise ValueError(f'workpieces[{index}] 必须是对象')
        wp_uid = workpiece.get('uid')
        if not isinstance(wp_uid, str) or not wp_uid.strip() or wp_uid in ids:
            raise ValueError('工件 uid 必须是非空且不重复的字符串')
        ids.append(wp_uid)
        for field in ('robot_tcp_id', 'weld_process_id'):
            if type(workpiece.get(field)) is not int or workpiece[field] <= 0:
                raise ValueError(f'workpieces[{index}].{field} 必须是实际存在的正整数 ID')
        if not isinstance(workpiece.get('nodes'), list):
            raise ValueError(f'workpieces[{index}].nodes 必须是数组；数据库详情不是任务 Goal')
        if not workpiece['nodes'] and not workpiece.get('scanning_feature_points'):
            raise ValueError('工件必须有焊接单元或扫描轨迹；本脚本不会生成运动路径')
    if live:
        serialized = json.dumps(task, ensure_ascii=False).lower()
        if task.get('demonstration_only') or any(marker in serialized for marker in
                ('apidoc_scan_only', 'not_submitted', 'demo-', '仅格式演示')):
            raise ValueError('演示任务禁止下发；请提供经现场审核的真实任务，不能只改演示名称')
    return task


def load_task(path, expected_uid=None, live=False):
    task = parse_json(Path(path).read_text(encoding='utf-8-sig'))
    # Accept an actual ATWeldTask Goal envelope, not a JSON string of unknown shape.
    if isinstance(task, dict) and set(task) == {'json_data'}:
        if not isinstance(task['json_data'], str):
            raise ValueError('Goal.json_data 必须是 JSON 字符串')
        task = parse_json(task['json_data'])
    return validate_task(task, expected_uid, live)


def task_status(client, timeout):
    reply = client.task_command('get_task_status', timeout=timeout)
    if reply.status != 200:
        raise ValueError(f'状态查询失败：{reply.status} {reply.message}')
    status = parse_json(reply.data)
    if not isinstance(status, dict):
        raise ValueError('状态响应不是 JSON 对象')
    print('任务状态：', json.dumps(status, ensure_ascii=False), flush=True)
    if not status:
        print('空状态仅表示没有可用任务反馈，不证明机器人已停止或系统可安全执行。')
    return status


def feedback(message):
    # Keep raw errors/unknown fields; accepted or waiting is never reported as PASS.
    print('反馈：', message.status_message, flush=True)


def submit(client, task, timeout, wait):
    status = task_status(client, timeout)
    if status and str(status.get('project_status')) != '101006':
        raise ValueError('已有未完成或未知状态任务，拒绝覆盖；请现场核对，不自动销毁任务')
    print('即将下发（不自动启动）：', task['project']['uid'], flush=True)
    handle = client.submit_task(task, feedback_callback=feedback, timeout=timeout)
    try:
        if not handle.accepted:
            raise ValueError('ROS Goal 被拒绝；任务未获 ROS 层受理')
        print('ROS 已受理，不代表业务成功。101007 表示等待启动，不是完成。', flush=True)
        print('保持本终端运行；确认准备完成后，在另一终端执行 start。', flush=True)
        _, ros_status, result = handle.wait_result(timeout=wait)
        # SDK already checks these; keep the example's success criterion explicit.
        if ros_status != 4 or str(parse_json(result).get('project_status')) != '101006':
            raise ValueError('任务没有正常完成：' + str(result))
        print('任务正常完成：', result, flush=True)
    finally:
        handle.release()  # Local resource cleanup only; not a stop/cancel command.


def start(client, expected_uid, timeout):
    status = task_status(client, timeout)
    if str(status.get('project_status')) != '101007':
        raise ValueError('仅允许在反馈为 101007（等待启动）时显式启动')
    # No current-task call when state is empty: some deployed servers dereference null.
    reply = client.task_command('get_current_task', timeout=timeout)
    if reply.status != 200:
        raise ValueError('无法读取当前任务，拒绝启动')
    validate_task(parse_json(reply.data), expected_uid, live=True)
    status = task_status(client, timeout)
    if (str(status.get('project_status')) != '101007'
            or status.get('project_uid') != expected_uid):
        raise ValueError('状态/反馈 UID 已变化或缺失，拒绝启动')
    # This API is global, not UID-bound. Readback does NOT provide an ownership lock.
    reply = client.task_command('task_start', timeout=timeout)
    print('启动响应：', reply.status, reply.message, reply.data, flush=True)
    if reply.status != 200:
        raise ValueError('启动请求失败；不自动重试')
    print('启动请求成功不代表任务完成；请查看下发终端的反馈和最终结果。')


def positive_seconds(text):
    value = float(text)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError('时间必须是有限正数')
    return value


def main(argv=None, client_factory=None):
    parser = argparse.ArgumentParser(description='自动作业 Python SDK：检查、状态、下发、显式启动')
    sub = parser.add_subparsers(dest='command')
    check = sub.add_parser('check', help='离线检查，不连接设备')
    check.add_argument('--input', default=str(ROOT / 'docs/scan-only-goal.json'))
    for command in ('status', 'submit', 'start'):
        p = sub.add_parser(command)
        p.add_argument('--timeout', type=positive_seconds, default=10)
        if command != 'status':
            p.add_argument('--expected-uid', required=True)
            p.add_argument('--confirm-site-safe', action='store_true',
                           help='已审核真实轨迹/工艺/TCP/坐标系，现场有人监护，且仅有本控制方')
        if command == 'submit':
            p.add_argument('--input', required=True)
            p.add_argument('--confirm-data-reset', action='store_true',
                           help='允许下发清理旧任务日志/焊接数据、覆盖临时任务及准备设备')
            p.add_argument('--wait', type=positive_seconds, default=600,
                           help='等待最终结果的秒数；超时不会停止任务（默认 600）')
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        print('\n首次运行：python3 auto_task.py check（仅检查仓库演示结构，不连接设备）')
        return 0
    if args.command == 'check':
        task = load_task(args.input)
        print(json.dumps(task, ensure_ascii=False, indent=2))
        print('基础结构检查通过；未连接设备，未验证 ID 存在、完整业务字段或轨迹安全。')
        return 0
    if args.command in ('submit', 'start'):
        if not args.expected_uid.strip() or not args.confirm_site_safe:
            parser.error('必须指定非空 --expected-uid 和 --confirm-site-safe')
        if args.command == 'submit' and not args.confirm_data_reset:
            parser.error('下发有数据清理副作用，必须显式提供 --confirm-data-reset')
    task = load_task(args.input, args.expected_uid, live=True) if args.command == 'submit' else None
    if client_factory is None:
        # Use this checkout's SDK. ROS2 + matching weld_interfaces must still be sourced.
        sys.path.insert(0, str(ROOT / 'sdk/python'))
        from aotai_sdk import Client
        client_factory = Client
    print(WARNING, flush=True)
    with client_factory() as client:
        if args.command == 'status':
            task_status(client, args.timeout)
        elif args.command == 'submit':
            submit(client, task, args.timeout, args.wait)
        else:
            start(client, args.expected_uid, args.timeout)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\n已结束本地等待。' + WARNING, file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        print(f'FAIL：{error}；raw={getattr(error, "raw", None)!r}', file=sys.stderr)
        if isinstance(error, ImportError):
            print('在线调用需要 ROS2/rclpy 和匹配的 weld_interfaces；请在已配置的 Ubuntu '
                  '虚拟机运行并 source ROS/接口环境。Windows 普通 Python 不足以运行本 SDK。',
                  file=sys.stderr)
        print(WARNING, file=sys.stderr)
        raise SystemExit(2)
