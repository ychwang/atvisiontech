#!/usr/bin/env python3
"""Inspect configuration or receive robot status; never initialize or control hardware.

Offline by default. --connect enables only robot_config or a bounded subscription.
Receiving status frames is not proof of device connection, freshness or readiness.
"""

import argparse
import json
import math
import threading


def config_snapshot(client, timeout):
    reply = client.robot_config(timeout=timeout)
    return {name: getattr(reply, name) for name in (
        'status', 'robot_type', 'robot_subtype', 'robot_ip', 'message')}


def status_snapshot(message):
    result = {name: list(getattr(message, name)) for name in (
        'tcp_pos', 'transformed_tcp_pos', 'tcp_v', 'joint_pos', 'joint_v')}
    for name, values in result.items():
        if any(not math.isfinite(value) for value in values):
            raise ValueError(f'{name} contains a non-finite value')
    # Preserve empty arrays and disconnected state rather than inventing readiness.
    result.update({name: getattr(message, name) for name in (
        'robot_mode', 'digital_input', 'connect_status', 'timestamp')})
    return result


def collect_status(client, message_type, sample_count, timeout):
    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or not 1 <= sample_count <= 1000:
        raise ValueError('sample_count must be an integer from 1 to 1000')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be finite and positive')
    samples, errors = [], []
    done = threading.Event()
    lock = threading.Lock()

    def callback(message):
        with lock:
            if done.is_set():
                return
            try:
                samples.append(status_snapshot(message))
            except (AttributeError, TypeError, ValueError) as error:
                errors.append(str(error))
                done.set()
            if len(samples) >= sample_count:
                done.set()

    subscription = client.subscribe(
        message_type, '/at/robot/get_real_time_status', callback)
    try:
        completed = done.wait(timeout)
        with lock:
            done.set()
            if errors:
                raise ValueError(errors[0])
            if not completed:
                raise TimeoutError(f'received {len(samples)}/{sample_count} frames within {timeout:g}s')
            return list(samples)
    finally:
        subscription.release()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=('config', 'monitor'), default='config')
    parser.add_argument('--connect', action='store_true')
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--timeout', type=float, default=5)
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('--timeout must be finite and positive')
    if not 1 <= args.samples <= 1000:
        parser.error('--samples must be between 1 and 1000')
    if not args.connect:
        print('OFFLINE: add --connect for configuration query or passive monitoring; no robot commands sent.')
        return 0

    from aotai_sdk import Client, ApiError
    try:
        with Client(node_name='robot_inspect_example') as client:
            if args.case == 'config':
                result = {'case': 'config', 'response': config_snapshot(client, args.timeout)}
            else:
                from weld_interfaces.msg import ATRobotStatus
                samples = collect_status(client, ATRobotStatus, args.samples, args.timeout)
                result = {
                    'case': 'monitor', 'sample_count': len(samples), 'samples': samples,
                    'timestamps_strictly_increasing': (
                        all(b['timestamp'] > a['timestamp'] for a, b in zip(samples, samples[1:]))
                        if len(samples) > 1 else None),
                    'last_connect_status': samples[-1]['connect_status'],
                }
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        print('PASS: query/receipt only; not proof of device connection, motion completion or safety.')
        return 0
    except (ApiError, AttributeError, TypeError, ValueError, TimeoutError) as error:
        print(f'FAIL: {error}; no retry or device control was attempted.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
