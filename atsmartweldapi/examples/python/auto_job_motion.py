#!/usr/bin/env python3
"""Preview three process-linked line seams from live TCP; live seam execution is gated."""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import sys
import threading
import time

import auto_task

ROOT = Path(__file__).resolve().parents[2]
AXES = (('Y', 1), ('X', 0), ('Z', 2))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pose_values(pose):
    require(len(pose) == 6 and all(type(v) in (int, float) and math.isfinite(v)
                                  for v in pose), '位姿必须为 6 个有限数')
    return list(pose)


def build_job(origin, run_id, tcp_id, process_id, class_id, speed=10, *, node_type=0):
    """No frame conversion: live reference MUST equal the reviewed world/base frame."""
    origin = pose_values(origin)
    require(type(node_type) is int and node_type in (0, 3), '只支持直线焊缝或历史空跑节点')
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,47}', run_id), 'run-id 格式错误')
    require(all(type(i) is int and i > 0 for i in (tcp_id, process_id, class_id)),
            'TCP、工艺、工艺类别必须为真实正整数 ID')
    require(type(speed) in (float, int) and math.isfinite(speed) and 0 < speed <= 10,
            '首次空跑脚本限速 0 < speed <= 10 mm/s')
    base = auto_task.parse_json((ROOT / 'examples/data/field-create-templates.json').read_text())['project']
    project = copy.deepcopy(base['project'])
    uid = 'API_MOTION_' + run_id
    project.update(id=0, name=uid, uid=uid, robot_tcp_id=tcp_id,
                   direct_run=0, loop_execution=0, need_reservation=0, need_digital_start=0,
                   need_confirm_after_scanning=0, need_confirm_after_planning=0)
    wp = copy.deepcopy(base['workpieces'][0])
    wp.update(id=0, name=uid + '_workpiece', uid=uid + '_wp', robot_tcp_id=tcp_id,
              weld_process_id=process_id, process_class_id=class_id, workpiece_type=0,
              workpiece_db_id=0,  # Inline non-scanning paths have no workpiece-library reference.
              node_path_frame='base', tracker_type=2, laser_task_type=0, need_scanning=0)
    prototype, nodes, target, previous = wp['nodes'][0], [], list(origin), ''
    for axis, index in AXES:
        start = list(target)
        target[index] += 200.0
        node = copy.deepcopy(prototype)
        node_uid = uid + '_' + axis
        point = dict(zip(('x', 'y', 'z', 'w', 'p', 'r'), target))
        point.update(uid=node_uid + '_point', valid=True)
        node.update(uid=node_uid, name=axis + ('+200mm SEAM' if node_type == 0 else '+200mm (NO ARC)'), node_type=node_type,
                    predecessor_node_uid=previous, path=[point], is_multi=False,
                    laser_enable=0, laser_task_type=0, weld_process_id=process_id,
                    process_class_id=class_id,
                    dry_run_path_params={'motion_type': 0, 'speed': speed, 'acc': 0.1})
        if node_type == 0:
            # A line seam is a start/end pair, not a single travel destination.
            # Motion parameters come from the linked welding process, not the
            # safe-point dry_run_path_params field. No claim of arc inhibition.
            start_point = dict(zip(('x', 'y', 'z', 'w', 'p', 'r'), start))
            start_point.update(uid=node_uid + '_start', valid=True)
            node['path'] = [start_point, point]
            node.pop('dry_run_path_params', None)
        nodes.append(node)
        previous = node_uid
    wp['nodes'] = nodes
    task = {'project': project, 'workpieces': [wp]}
    auto_task.validate_task(task, live=True)
    return task


def same_subset(actual, expected, where='readback'):
    """Compare every sent field; permit server-added metadata only."""
    if isinstance(expected, dict):
        require(isinstance(actual, dict), where + ': 非对象')
        for key, value in expected.items():
            require(key in actual, where + ': 缺字段 ' + key)
            same_subset(actual[key], value, where + '.' + key)
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected), where + ': 数组不匹配')
        for index, value in enumerate(expected):
            same_subset(actual[index], value, f'{where}[{index}]')
    else:
        require(type(actual) is type(expected) and actual == expected, where + ': 值/类型不匹配')


def json_reply(reply):
    require(reply.status == 200, f'接口拒绝：{reply.status} {reply.message}')
    return auto_task.parse_json(reply.data)


def generic(client, typ, name, identity='', data=''):
    return json_reply(client.call(typ, '/at/data/' + name,
                                  {'id': str(identity), 'data': data}, timeout=10))


def read_system_status(client):
    from std_msgs.msg import String
    arrived, samples = threading.Event(), []
    started = time.time() * 1000

    def receive(message):
        if not samples:
            samples.append(message.data)
            arrived.set()

    subscription = client.subscribe(String, '/at/system/status', receive)
    try:
        require(arrived.wait(5), '等待系统空闲状态超时')
        state = auto_task.parse_json(samples[0])
        stamp = float(state['timestamp'])
        require(math.isfinite(stamp) and started - 1000 <= stamp <= time.time() * 1000 + 1000,
                '系统空闲消息时间戳过期/无效')
        return state
    finally:
        subscription.release()


def verify_idle(client, recover_failed_uid=None):
    state = auto_task.task_status(client, 10)
    if not state or str(state.get('project_status')) == '101006':
        return
    # Narrow, explicit recovery of the reviewed pre-motion workpiece-ID failure.
    # Other terminal/unknown states remain blocked; this never clears a task.
    require(recover_failed_uid and state.get('project_uid') == recover_failed_uid
            and str(state.get('project_status')) == '1011008'
            and state.get('msg') == 'Workpiece id does not exist.',
            '已有未完成/未知任务；不覆盖，不自动销毁')
    current = json_reply(client.task_command('get_current_task', timeout=10))
    if current == {}:
        # Cleanup can clear the live task while retaining its terminal feedback.
        # Verify the persisted definition instead; never invent the old task.
        from weld_interfaces.srv import ATStringGeneric
        project_id = int(state.get('project_id', 0))
        require(project_id > 0, '失败反馈没有有效工程 ID；不恢复')
        current = generic(client, ATStringGeneric, 'workpiece_task_detail', project_id)
        require(int(current.get('project', {}).get('id', 0)) == project_id,
                '失败工程回读 ID 不一致')
    auto_task.validate_task(current, recover_failed_uid, live=True)
    require(all(wp.get('laser_task_type') == 0 and wp.get('nodes')
                and all(node.get('node_type') == 3 for node in wp['nodes'])
                for wp in current['workpieces']), '只允许恢复已核验的纯空跑准备失败任务')
    require(read_system_status(client).get('task_info', {}).get('is_idle') is True,
            '失败任务尚未清理为空闲；不重新下发')
    robot_ready(client)  # Read-only: never reconnect or power on during recovery.
    require(auto_task.task_status(client, 10) == state, '核验期间任务状态变化；不重新下发')


def robot_ready(client, connect=False, power=False, require_power=False):
    config = client.robot_config(timeout=10)
    require(config.status == 200 and config.robot_type == 'xCore'
            and config.robot_subtype == 'CR7' and config.robot_ip == '192.168.1.160',
            '仅支持已审核的 xCore/CR7/192.168.1.160；不会自动重新初始化')
    state = json_reply(client.robot_status(timeout=10))
    if state.get('connect_status') is not True and connect:
        reply = client.robot_connect(True, timeout=10)
        require(reply.status == 200, '机器人连接失败')
        state = json_reply(client.robot_status(timeout=10))
    require(state.get('connect_status') is True, '机器人尚未连接')
    if state.get('power_status') is not True and power:
        reply = client.robot_power(True, timeout=10)
        require(reply.status == 200 and not reply.message,
                '上电失败或有警告；不继续，不自动更改示教器模式')
        state = json_reply(client.robot_status(timeout=10))
    require(state.get('motion_status') in (0, False), '机器人运动状态不是静止')
    if connect or require_power:
        require(state.get('power_status') is True, '机器人未上电；现场上电后重试或显式 --power-on')
    return pose_values(client.robot_pose(timeout=10).cur_pos)


def verify_process(client, typ, process_id, tcp_id):
    detail = json_reply(client.process_detail(process_id, timeout=10))
    require(int(detail['id']) == process_id and type(detail['class_id']) is int
            and detail['class_id'] > 0, '工艺身份不匹配')
    current_tcp = generic(client, typ, 'robot_tcp_calibration_current')
    require(int(current_tcp['id']) == tcp_id, '当前 TCP 数据库选择与请求不一致')
    config = generic(client, typ, 'system_config_detail_by_process', process_id)
    require(int(config['configPara']['robot_tcp_id']) == tcp_id, '工艺关联 TCP 与请求 TCP 不一致')
    robot = config['robotConfig']
    require(int(robot['robot_type']) == 1 and robot['robot_model'] == 'CR7'
            and robot['robot_ip'] == '192.168.1.160', '工艺关联的机器人不是目标 xCore/CR7')
    return detail['class_id']


def create_project(client, typ, task, save):
    payload = {'name': task['project']['name'], **copy.deepcopy(task)}
    save('create-request.json', payload)  # Durable before the first database write.
    result = generic(client, typ, 'workpiece_task_add', data=json.dumps(payload, ensure_ascii=False))
    save('create-response.json', result)
    pid, ids = result['project_id'], result['workpieceIds']
    require(type(pid) is int and pid > 0 and isinstance(ids, list) and len(ids) == 1
            and type(ids[0]) is int and ids[0] > 0, '工程创建返回 ID 无效；禁止重试')
    expected = copy.deepcopy(task)
    expected['project']['id'] = str(pid)  # Detail uses string; Action uses integer.
    expected['workpieces'][0]['id'] = ids[0]
    detail = generic(client, typ, 'workpiece_task_detail', pid)
    save('create-readback.json', detail)
    require(detail.get('task_name') == payload['name'], '工程名称回读不匹配')
    same_subset(detail, expected)
    result_task = copy.deepcopy(task)
    result_task['project']['id'] = pid
    result_task['workpieces'][0]['id'] = ids[0]
    save('task-goal.json', result_task)
    return result_task


def verify_preview(workpieces, task, speed, expected_blend_radius=0):
    require(all(node.get('node_type') == 3 for wp in task['workpieces'] for node in wp['nodes']),
            '焊缝预规划不能使用历史空跑点校验；必须核验工艺、起收弧及过渡路径')
    require(type(expected_blend_radius) in (int, float) and expected_blend_radius in (0, 3),
            '交融期望值必须显式为 0 或已审核的后端默认 3 mm')
    require(isinstance(workpieces, list) and len(workpieces) == 1, '预规划工件数不匹配')
    wp = workpieces[0]
    wanted = task['workpieces'][0]
    require(wp.get('uid') == wanted['uid'], '预规划工件 UID 不一致')
    route = wp['route_plan_result']
    require(route.get('status') == 'success', '没有成功的服务端预规划')
    segments = [segment for weld in route['weld_trajectory']
                for path in weld['pass_trajectory'] for segment in path['path_attribute']]
    require(len(segments) == 3, '预规划不恰好包含三段；禁止额外过渡/返回路径')
    for segment, node in zip(segments, wanted['nodes']):
        require(segment.get('is_arcing') is False and segment.get('is_arced') is False,
                '预规划存在起弧/焊接或缺失禁焊标志')
        require(segment.get('move_type') == 0 and segment.get('trajs_uid') == node['uid'],
                '预规划不是请求的直线/顺序')
        params = segment['motion_params']
        require(all(type(params.get(k)) in (int, float) and math.isfinite(params[k])
                    for k in ('speed', 'acc', 'blend_radius'))
                and 0 < params['speed'] <= speed and 0 < params['acc'] <= 0.1
                and params['blend_radius'] == expected_blend_radius,
                '预规划速度/加速度/交融不符合要求')
        end = pose_values(segment['path']['end_point'])
        target = [node['path'][0][k] for k in ('x', 'y', 'z', 'w', 'p', 'r')]
        require(all(abs(a - b) <= 1e-6 for a, b in zip(end, target)), '预规划目标被修改')



def verify_seam_preview(workpieces, task, speed=10, safe_distance=10, expected_blend_radius=3):
    """Strict contract for three continuous line seams, single pass, no weaving.

    Arc markers are logical seam boundaries, NOT evidence of physical inhibition.
    Caller must independently verify the welder inhibition and unchanged process.
    """
    require(type(safe_distance) in (int, float) and safe_distance == 10,
            '仅核验当前工艺的 10 mm 接近/退枪路径')
    require(type(speed) in (int, float) and math.isfinite(speed) and 0 < speed <= 10,
            '焊缝限速必须在 0..10 mm/s 内')
    require(type(expected_blend_radius) in (int, float) and expected_blend_radius in (0, 3),
            '交融必须为已审核的 0 或 3 mm')
    require(len(task['workpieces']) == 1, '仅支持一个工件')
    wanted = task['workpieces'][0]
    nodes = wanted['nodes']
    require(len(nodes) == 3 and all(n.get('node_type') == 0 and len(n['path']) == 2
            and n.get('is_multi') is False and n.get('weld_process_id') == wanted['weld_process_id']
            for n in nodes), '必须为同工艺的三条单道直线焊缝')
    def point(value):
        return pose_values([value[k] for k in ('x', 'y', 'z', 'w', 'p', 'r')])
    def close(a, b, xyz=1e-5, angle=1e-6):
        return math.dist(a[:3], b[:3]) <= xyz and max(abs(x-y) for x,y in zip(a[3:], b[3:])) <= angle
    points = [point(nodes[0]['path'][0])]
    for node, (_, axis) in zip(nodes, AXES):
        start, end = map(point, node['path'])
        require(close(start, points[-1]), '焊缝不连续')
        expected = list(start); expected[axis] += 200
        require(close(end, expected), '焊缝不是请求的固定姿态 Y/X/Z 各 200 mm')
        points.append(end)
    def safe(pose):
        x,y,z,w,p,r = pose
        direction = (math.cos(r)*math.sin(p)*math.cos(w)+math.sin(r)*math.sin(w),
                     math.sin(r)*math.sin(p)*math.cos(w)-math.cos(r)*math.sin(w),
                     math.cos(p)*math.cos(w))
        return [value+safe_distance*d for value,d in zip((x,y,z),direction)] + [w,p,r]
    targets = [safe(points[0]), points[0], *points[1:], safe(points[-1])]
    require(isinstance(workpieces, list) and len(workpieces) == 1
            and workpieces[0].get('uid') == wanted['uid'], '预规划工件不匹配')
    route = workpieces[0]['route_plan_result']
    require(route.get('status') == 'success' and len(route['weld_trajectory']) == 1,
            '预规划不是一个连续焊缝组')
    passes = route['weld_trajectory'][0]['pass_trajectory']
    require(len(passes) == 1, '预规划不是单道')
    segments = passes[0]['path_attribute']
    require(len(segments) == 6, '必须恰好为接近、起点、三焊缝、退枪六段')
    expected_uids = ['', '', *[n['uid'] for n in nodes], '']
    last = points[0]
    for i, (segment, target, uid) in enumerate(zip(segments, targets, expected_uids)):
        require(segment.get('is_arcing') is (i == 1)
                and segment.get('is_arced') is (i == 4)
                and segment.get('is_wait') is (i not in (2,3))
                and segment.get('is_plan_path') is False
                and segment.get('move_type') == 0 and segment.get('trajs_uid') == uid
                and segment.get('path_type') == (1 if i == 1 else 2 if i == 4 else 0),
                '焊缝顺序、运动类型或起收弧边界不符')
        params = segment['motion_params']
        require(all(type(params.get(k)) in (int,float) and math.isfinite(params[k])
                    for k in ('speed','acc','blend_radius'))
                and 0 < params['speed'] <= speed and 0 < params['acc'] <= .1
                and params['blend_radius'] == expected_blend_radius
                and params.get('run_time') == 0 and params.get('xd') == [0]*6,
                '焊缝预规划速度/加速度/交融或运动参数不符')
        start = pose_values(segment['path']['start_point'])
        end = pose_values(segment['path']['end_point'])
        require(close(start,last,1 if i == 0 else 1e-5,.001 if i == 0 else 1e-6)
                and close(end,target), '焊缝或接近/退枪路径位姿被修改')
        last = end
    return targets[-1]


def check_origin(client, origin):
    current = robot_ready(client, require_power=True)
    require(math.dist(current[:3], origin[:3]) <= 1.0
            and max(abs(a - b) for a, b in zip(current[3:], origin[3:])) <= 0.001,
            '起点/TCP 已变化；停止后续操作，不自动重建轨迹')


def submit_and_start(client, task, origin, speed, save, wait=600, recover_failed_uid=None,
                     expected_blend_radius=0):
    require(all(node.get('node_type') == 3 for wp in task['workpieces'] for node in wp['nodes']),
            '焊缝执行尚未验证禁焊与预规划契约；禁止用空跑流程下发或启动')
    uid = task['project']['uid']
    verify_idle(client, recover_failed_uid)
    check_origin(client, origin)
    ready, feedback_fault = threading.Event(), []

    def receive(message):
        print('反馈：', message.status_message, flush=True)
        try:
            value = auto_task.parse_json(message.status_message)
            code = str(value['project_status'])
            if code == '101007' and value.get('project_uid') == uid:
                ready.set()
            elif code not in ('101001', '101002', '101007'):
                feedback_fault.append(value)
                ready.set()
        except (ValueError, KeyError, TypeError) as error:
            feedback_fault.append(str(error))
            ready.set()

    save('submit-intent.json', {'uid': uid, 'state': 'outcome unknown until feedback'})
    handle = client.submit_task(task, receive, timeout=10)
    try:
        require(handle.accepted, 'ROS Goal 拒绝；未启动')
        require(ready.wait(60), '60 秒内没有收到本任务 101007；不启动，不重发')
        require(not feedback_fault, '准备失败/异常反馈：' + repr(feedback_fault))
        same_subset(json_reply(client.task_command('get_current_task', timeout=10)), task)
        preview = json_reply(client.task_command('get_workpiece_plan_path', timeout=10))
        save('server-preview.json', preview)
        verify_preview(preview, task, speed, expected_blend_radius)
        check_origin(client, origin)
        save('start-intent.json', {'uid': uid, 'no_arc': True})
        auto_task.start(client, uid, 10)  # Checks current task and status UID immediately before start.
        _, status, result = handle.wait_result(timeout=wait)
        save('task-result.json', {'ros_status': status, 'result': result})
        require(status == 4 and str(auto_task.parse_json(result)['project_status']) == '101006',
                '任务未正常完成')
        actual = robot_ready(client, require_power=True)
        final = task['workpieces'][0]['nodes'][-1]['path'][0]
        require(math.dist(actual[:3], [final[k] for k in ('x', 'y', 'z')]) <= 2,
                '业务结束但末端位置未到目标（2 mm 容差），请现场检查')
        save('final-pose.json', actual)
        print('任务正常结束且末端位置回读通过；不自动返回或下电。')
    finally:
        handle.release()  # Does NOT stop hardware.


def main(argv=None, client_factory=None, service_type=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--preview', action='store_true', help='只读实际起点/工艺并输出任务，不连接/上电/写库')
    mode.add_argument('--execute', action='store_true', help='暂不可用：焊缝执行须先完成禁焊、工艺及路径校验适配')
    parser.add_argument('--tcp-id', type=int)
    parser.add_argument('--process-id', type=int)
    parser.add_argument('--run-id')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--speed', type=auto_task.positive_seconds, default=10)
    parser.add_argument('--expected-blend-radius', type=float, choices=(0, 3), default=0,
                        help='校验服务端交融半径，默认0；现场审核后可显式选择3，不修改后端')
    parser.add_argument('--power-on', action='store_true')
    parser.add_argument('--confirm-site-safe', action='store_true')
    parser.add_argument('--confirm-no-arc', action='store_true', help='现场已独立禁焊，不只依赖软件参数')
    parser.add_argument('--confirm-frame-and-tcp', action='store_true',
                        help='当前参考系、世界系、任务基座系对齐，TCP ID 对应当前工具，角度为 rad')
    parser.add_argument('--allow-data-reset', action='store_true')
    parser.add_argument('--recover-failed-uid',
                        help='仅显式恢复此 UID 的工件库 ID 准备失败；须核实系统空闲、机器人静止')
    args = parser.parse_args(argv)
    if not (args.preview or args.execute):
        parser.print_help()
        return 0
    if (not args.run_id or not args.output or args.tcp_id is None or args.process_id is None
            or not args.confirm_frame_and_tcp):
        parser.error('需要 --run-id --output --tcp-id --process-id --confirm-frame-and-tcp')
    # Validate arguments without a ROS connection or invented live coordinates.
    build_job([0.0] * 6, args.run_id, args.tcp_id, args.process_id, 1, args.speed)
    if args.execute and not (args.confirm_site_safe and args.confirm_no_arc and args.allow_data_reset):
        parser.error('执行还需要 --confirm-site-safe --confirm-no-arc --allow-data-reset')
    if args.execute:
        parser.error('当前生成真实焊缝；执行校验尚未适配，暂仅支持 --preview，不写库、不下发、不启动')
    if args.power_on and not args.execute:
        parser.error('--power-on 仅用于显式 execute')
    if args.recover_failed_uid and not args.execute:
        parser.error('--recover-failed-uid 仅用于显式 execute')
    args.output.mkdir(parents=True, exist_ok=False)  # Same run cannot silently overwrite evidence.

    def save(name, value):
        import os
        with (args.output / name).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())

    save('run-intent.json', {'time': time.time(), 'run_id': args.run_id, 'execute': args.execute,
                           'recover_failed_uid': args.recover_failed_uid,
                           'expected_blend_radius': args.expected_blend_radius})
    if client_factory is None:
        sys.path.insert(0, str(ROOT / 'sdk/python'))
        from aotai_sdk import Client
        from weld_interfaces.srv import ATStringGeneric
        client_factory, service_type = Client, ATStringGeneric
    print(auto_task.WARNING, flush=True)
    with client_factory() as client:
        verify_idle(client, args.recover_failed_uid)
        class_id = verify_process(client, service_type, args.process_id, args.tcp_id)
        origin = robot_ready(client, connect=args.execute, power=args.power_on)
        save('origin.json', origin)
        task = build_job(origin, args.run_id, args.tcp_id, args.process_id, class_id, args.speed)
        save('generated-task.json', task)
        print(json.dumps(task, ensure_ascii=False, indent=2), flush=True)
        if args.execute:
            verify_idle(client, args.recover_failed_uid)
            task = create_project(client, service_type, task, save)
            submit_and_start(client, task, origin, args.speed, save,
                             recover_failed_uid=args.recover_failed_uid,
                             expected_blend_radius=args.expected_blend_radius)
        else:
            print('只读预览完成：没有连接/上电命令、写库、下发或启动。')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as error:
        print(f'停止后续请求：{error}；raw={getattr(error, "raw", None)!r}', file=sys.stderr)
        print(auto_task.WARNING + ' 已写入的工程不自动删除；设备状态不自动恢复。', file=sys.stderr)
        raise SystemExit(2)
