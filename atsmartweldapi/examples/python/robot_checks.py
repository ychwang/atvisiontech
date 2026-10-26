#!/usr/bin/env python3
"""Bounded robot commissioning checks, offline by default; never sends motion.

preflight queries status (the server may reconnect its driver) and receives frames.
sampling explicitly enables driver sampling; no sampling-disable API is assumed.
power-cycle applies configured default TCP/load, tests stop while idle, then powers
back off. It is NOT a test of stopping a moving robot or a safety certification.
"""
import argparse
import json
import math
import signal

from robot_inspect import collect_status, config_snapshot


def log(operation, **fields):
    print(json.dumps({'operation': operation, **fields}, ensure_ascii=False, allow_nan=False), flush=True)


def checked(reply, operation):
    log(operation, status=reply.status, message=reply.message,
        result=getattr(reply, 'result', None))
    if reply.status != 200 or reply.message:
        raise RuntimeError(f'{operation}: rejected or warning: {reply.status} {reply.message}')


def read_state(client, timeout, robot_type, powered):
    reply = client.robot_status(timeout=timeout)
    if reply.status != 200:
        raise ValueError('robot_status rejected')
    state = json.loads(reply.data)
    log('state', state=state)
    if not isinstance(state, dict) or state.get('robot_type') != robot_type:
        raise ValueError('unexpected robot status identity')
    if state.get('connect_status') is not True or state.get('power_status') is not powered:
        raise ValueError('robot must be connected with the expected power state')
    if type(state.get('motion_status')) is not int or state['motion_status'] != 0:
        raise ValueError('robot is not confirmed idle')
    if type(state.get('subscribe_status')) is not bool:
        raise ValueError('invalid sampling state')
    return state


def verify_frames(frames):
    for frame in frames:
        if frame['connect_status'] != 1:
            raise ValueError('disconnected status frame')
        for field in ('tcp_pos', 'transformed_tcp_pos', 'joint_pos', 'tcp_v', 'joint_v'):
            if len(frame[field]) != 6 or any(not math.isfinite(x) for x in frame[field]):
                raise ValueError(f'invalid {field}')
        if any(abs(x) > 1e-6 for field in ('tcp_v', 'joint_v') for x in frame[field]):
            raise ValueError('nonzero velocity during stationary checks')
        if type(frame['timestamp']) is not int or frame['timestamp'] <= 0:
            raise ValueError('invalid timestamp')
    if any(b['timestamp'] <= a['timestamp'] for a, b in zip(frames, frames[1:])):
        raise ValueError('non-increasing timestamps')
    log('monitor', sample_count=len(frames), first=frames[0], last=frames[-1],
        timestamp_units='raw message units; not clock synchronization proof')


def run(client, types, expected, case, timeout=5, samples=20, rounds=3, expected_power=False):
    # Validate before any request, including calls made directly by Python users.
    if case not in ('preflight', 'sampling', 'power-cycle'):
        raise ValueError('unknown case')
    if type(expected_power) is not bool or (expected_power and case != 'preflight'):
        raise ValueError('existing powered state is supported only for read-only preflight')
    if not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError('timeout must be finite, positive and <=30')
    if type(samples) is not int or not 2 <= samples <= 1000:
        raise ValueError('samples must be an integer from 2 to 1000')
    if type(rounds) is not int or not 1 <= rounds <= 20:
        raise ValueError('rounds must be an integer from 1 to 20')
    if len(expected) != 3 or any(not isinstance(x, str) or not x.strip() for x in expected):
        raise ValueError('expected robot type, subtype and IP are required')
    for index in range(rounds):
        config = config_snapshot(client, timeout)
        log('config', round=index + 1, response=config)
        if config['status'] != 200 or tuple(config[k] for k in ('robot_type', 'robot_subtype', 'robot_ip')) != tuple(expected):
            raise ValueError('robot identity mismatch')
        read_state(client, timeout, expected[0], expected_power)
        pose = client.robot_pose(timeout=timeout)
        values = {k: list(getattr(pose, k)) for k in ('cur_pos', 'joint_pos', 'flan_pos')}
        if pose.status not in (0, 200) or any(len(v) != 6 or any(not math.isfinite(x) for x in v) for v in values.values()):
            raise ValueError('invalid pose')
        log('pose', status=pose.status, **values)
    coord = client.call(types['coord'], '/at/robot/get_coord', {'mode': 0, 'handeye': []}, timeout=timeout)
    if coord.status != 200 or len(coord.result) != 1 or coord.result[0] not in range(7):
        raise ValueError('invalid coordinate enum')
    scale = client.call(types['scale'], '/at/robot/get_speed_scale', {}, timeout=timeout)
    if scale.status != 200 or not math.isfinite(scale.speed_scale) or not 0 <= scale.speed_scale <= 1:
        raise ValueError('invalid speed scale')
    log('settings', coordinate=list(coord.result), speed_scale=scale.speed_scale)
    if case == 'sampling':
        checked(client.robot_subscribe(timeout=timeout), 'enable_sampling')
    state = read_state(client, timeout, expected[0], expected_power)
    if state['subscribe_status'] is not True:
        raise ValueError('sampling is not enabled')
    verify_frames(collect_status(client, types['status'], samples, timeout))
    if case != 'power-cycle':
        return
    read_state(client, timeout, expected[0], False)
    # All above checks must pass. No retries on control requests, including timeout.
    # A timed-out power-on may have executed: attempt power-off once in finally.
    try:
        checked(client.robot_power(True, timeout=timeout), 'power_on')
        read_state(client, timeout, expected[0], True)
        verify_frames(collect_status(client, types['status'], samples, timeout))
        checked(client.robot_stop(timeout=timeout), 'stop_while_idle')
        read_state(client, timeout, expected[0], True)
    finally:
        try:
            checked(client.robot_power(False, timeout=timeout), 'restore_power_off')
            read_state(client, timeout, expected[0], False)
        except BaseException:
            log('CLEANUP_FAILED', action='Power state unknown: onsite operator must verify and use emergency stop if needed. No automatic retry.')
            raise


def interrupted(signum, frame):
    raise KeyboardInterrupt(f'signal {signum}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--confirm-site-safe', action='store_true')
    parser.add_argument('--case', choices=('preflight', 'sampling', 'power-cycle'), default='preflight')
    parser.add_argument('--robot-type')
    parser.add_argument('--robot-subtype')
    parser.add_argument('--robot-ip')
    parser.add_argument('--timeout', type=float, default=5)
    parser.add_argument('--samples', type=int, default=20)
    parser.add_argument('--rounds', type=int, default=3)
    args = parser.parse_args(argv)
    if not args.execute:
        print('OFFLINE: no SDK client or robot requests; use --execute with expected identity.')
        return 0
    if args.case != 'preflight' and not args.confirm_site_safe:
        parser.error('sampling/power-cycle requires --confirm-site-safe and onsite supervision')
    if not all((args.robot_type, args.robot_subtype, args.robot_ip)):
        parser.error('explicit expected robot identity required')
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 30 or not 2 <= args.samples <= 1000 or not 1 <= args.rounds <= 20:
        parser.error('invalid timeout/sample/round bounds')
    from aotai_sdk import Client
    from weld_interfaces.srv import ATRobotLaserTcpGet, ATRobotGetSpeedScale
    from weld_interfaces.msg import ATRobotStatus
    previous_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP)}
    for sig in previous_handlers:
        signal.signal(sig, interrupted)
    try:
        with Client(node_name='robot_checks_example') as client:
            run(client, {'coord': ATRobotLaserTcpGet, 'scale': ATRobotGetSpeedScale, 'status': ATRobotStatus},
                (args.robot_type, args.robot_subtype, args.robot_ip), args.case, args.timeout, args.samples, args.rounds)
    except (Exception, KeyboardInterrupt) as error:
        log('FAIL', error=str(error), raw=repr(getattr(error, 'raw', None)))
        return 1
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
    log('PASS', case=args.case, limitation='No motion sent; not a safety certification or full interface acceptance.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
