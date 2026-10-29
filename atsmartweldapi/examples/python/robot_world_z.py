#!/usr/bin/env python3
"""Deployment-specific xCore CR7 world +Z test; OFFLINE by default.

Requires onsite supervision and separately audited driver units/frame. The audited
move_step driver uses WORLD, even when get_coord returns base=2. Never infer world
from base. No automatic retry/return; stop and power-off are attempted in finally.
This is not a hardware safety function. Network/process failure can defeat cleanup.
"""
import argparse
from collections import deque
import math
import signal
import threading
import time

from robot_checks import checked, interrupted, log, read_state, run as preflight
from robot_inspect import status_snapshot

# Field test 2026-10-23: manual-mode enabling failed and delayed stop/off replies.
# The automatic power-on path stays blocked. A separate existing-power path never
# calls power(True); use only after onsite mode correction and readiness verification.
DEPLOYMENT_BLOCKED = True


class Feedback:
    def __init__(self, client, message_type):
        self.lock = threading.Lock()
        self.queue = deque()
        self.error = None
        self.last_received = time.monotonic()
        self.last_stamp = None
        self.subscription = client.subscribe(message_type, '/at/robot/get_real_time_status', self.callback)

    def callback(self, msg):
        with self.lock:
            try:
                frame = status_snapshot(msg)
                if frame['connect_status'] != 1:
                    raise ValueError('robot feedback disconnected')
                for key in ('tcp_pos', 'transformed_tcp_pos', 'joint_pos', 'tcp_v', 'joint_v'):
                    if len(frame[key]) != 6:
                        raise ValueError('feedback arrays must have six finite values')
                stamp = frame['timestamp']
                if type(stamp) is not int or stamp <= 0 or (self.last_stamp is not None and stamp <= self.last_stamp):
                    raise ValueError('invalid/non-increasing feedback timestamp')
                self.last_stamp = stamp
                self.last_received = time.monotonic()
                if len(self.queue) >= 200:
                    raise ValueError('feedback processing fell behind')
                self.queue.append((self.last_received, frame))
            except Exception as error:
                self.error = error

    def take(self):
        with self.lock:
            if self.error:
                raise self.error
            if time.monotonic() - self.last_received > .5:
                raise TimeoutError('no fresh feedback for 0.5 s')
            frames = list(self.queue)
            self.queue.clear()
            return frames

    def close(self):
        self.subscription.release()


def evaluate(baseline, frame, distance):
    delta = [frame['tcp_pos'][i] - baseline[i] for i in range(3)]
    travelled = math.sqrt(sum(x*x for x in delta))
    if not math.isfinite(travelled) or travelled > distance + 1:
        raise ValueError('observed displacement exceeds test envelope')
    # Pose orientation is RPY radians in this audited xCore driver; wrap differences.
    if any(abs(math.atan2(math.sin(frame['tcp_pos'][i]-baseline[i]),
                          math.cos(frame['tcp_pos'][i]-baseline[i]))) > .02 for i in range(3, 6)):
        raise ValueError('unexpected orientation change')
    return delta, travelled


def move_once(client, types, distance=20., speed=10., monitor_factory=Feedback, use_existing_power=False):
    if type(use_existing_power) is not bool:
        raise ValueError('use_existing_power must be boolean')
    if DEPLOYMENT_BLOCKED and not use_existing_power:
        raise RuntimeError('Motion disabled: deployed manual-mode enable failed (-514/10012); stop/off responses timed out. Repair and verify before retrying.')
    if not (math.isfinite(distance) and 1 <= distance <= 20 and
            math.isfinite(speed) and 2.5 <= speed <= 10):
        raise ValueError('audited test bounds: 1..20 mm and 2.5..10 mm/s')
    preflight(client, types, ('xCore', 'CR7', '192.168.1.160'), 'preflight',
              timeout=5, samples=5, rounds=5, expected_power=use_existing_power)
    coord = client.call(types['coord'], '/at/robot/get_coord', {'mode': 0, 'handeye': []}, timeout=3)
    scale = client.call(types['scale'], '/at/robot/get_speed_scale', {}, timeout=3)
    if list(coord.result) not in ([1.], [2.]) or scale.speed_scale != 1.:
        raise ValueError('audited routing requires application coord=1/2 and speed_scale=1; no settings changed')
    motion_attempted = False
    feedback = None
    try:
        if use_existing_power:
            log('preserve_existing_power', limitation='No power-on or mode-switch request sent by this script; mode readiness was confirmed onsite.')
        else:
            checked(client.robot_power(True, timeout=5), 'power_on')
        read_state(client, 3, 'xCore', True)
        checked(client.robot_stop(timeout=3), 'clear_idle_motion_before_test')
        read_state(client, 3, 'xCore', True)
        baseline = list(client.robot_pose(timeout=3).cur_pos)
        log('motion_plan', frame='WORLD +Z (not inferred from application base enum)',
            distance_mm=distance, speed_mm_s=speed, feedback_start=baseline)
        feedback = monitor_factory(client, types['status'])
        warm_deadline = time.monotonic() + 2
        warm = 0
        while warm < 3:
            if time.monotonic() >= warm_deadline:
                raise TimeoutError('feedback not ready before motion')
            for _, frame in feedback.take():
                _, drift = evaluate(baseline, frame, distance)
                if drift > .1 or any(abs(x) > 1e-6 for key in ('tcp_v', 'joint_v') for x in frame[key]):
                    raise ValueError('robot moved before test command')
                warm += 1
            time.sleep(.01)
        # Flag BEFORE request: a timeout does not mean the server did not execute it.
        motion_attempted = True
        log('motion_request_begin', axis='WORLD +Z', distance_mm=distance, speed_mm_s=speed)
        checked(client.robot_move_step('Z', distance, speed, timeout=2), 'move_step_world_z')
        deadline = time.monotonic() + distance / speed + 4
        settled = 0
        previous = None
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError('requested displacement not confirmed in time; no retry')
            for received, frame in feedback.take():
                delta, travelled = evaluate(baseline, frame, distance)
                log('motion_feedback', timestamp=frame['timestamp'], delta_feedback_xyz_mm=delta,
                    displacement_mm=travelled, tcp_v=frame['tcp_v'])
                if previous is not None:
                    _, prev_frame = previous
                    dt = (frame['timestamp'] - prev_frame['timestamp']) / 1000.
                    segment = math.dist(frame['tcp_pos'][:3], prev_frame['tcp_pos'][:3])
                    if dt > 0 and segment/dt > 20:
                        raise ValueError('observed speed exceeds conservative 20 mm/s guard')
                    settled = settled + 1 if abs(travelled-distance) <= .3 and segment < .05 else 0
                previous = received, frame
                if settled >= 3:
                    return delta
            time.sleep(.01)
    except BaseException as error:
        log('TEST_ABORTED', error=str(error), raw=repr(getattr(error, 'raw', None)))
        raise
    finally:
        try:
            if motion_attempted:
                try:
                    checked(client.robot_stop(timeout=3), 'stop_after_motion_attempt')
                    read_state(client, 3, 'xCore', True)
                    pose = client.robot_pose(timeout=3)
                    log('pose_after_stop', cur_pos=list(pose.cur_pos), joint_pos=list(pose.joint_pos))
                    _, final_distance = evaluate(baseline, {'tcp_pos': list(pose.cur_pos)}, distance)
                    log('final_displacement', distance_mm=final_distance)
                except BaseException:
                    log('STOP_UNCONFIRMED', action='Onsite operator must verify immediately and use emergency stop if needed.')
                    raise
        finally:
            try:
                checked(client.robot_power(False, timeout=3), 'restore_power_off')
                read_state(client, 3, 'xCore', False)
            except BaseException:
                log('POWER_OFF_UNCONFIRMED', action='Onsite operator must verify immediately and use emergency stop if needed.')
                raise
            finally:
                if feedback is not None:
                    feedback.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--confirm-world-z-safe', action='store_true')
    parser.add_argument('--confirm-site-safe', action='store_true')
    parser.add_argument('--use-existing-power', action='store_true',
                        help='Requires already-powered/idle robot after onsite mode correction; does not call power(True); ends powered off.')
    args = parser.parse_args(argv)
    if not args.execute:
        print('OFFLINE: proposed WORLD +Z 20 mm at 10 mm/s; no client or device command.')
        return 0
    if not (args.confirm_world_z_safe and args.confirm_site_safe):
        parser.error('explicit WORLD direction approval and onsite safety confirmation required')
    if DEPLOYMENT_BLOCKED and not args.use_existing_power:
        parser.error('Motion disabled after field failure: manual-mode enable -514/10012 and delayed stop/off; no retry until repaired and verified.')
    from aotai_sdk import Client
    from weld_interfaces.srv import ATRobotLaserTcpGet, ATRobotGetSpeedScale
    from weld_interfaces.msg import ATRobotStatus
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP)}
    for sig in previous:
        signal.signal(sig, interrupted)
    try:
        with Client(node_name='robot_world_z_bounded') as client:
            delta = move_once(client, {'coord': ATRobotLaserTcpGet, 'scale': ATRobotGetSpeedScale, 'status': ATRobotStatus},
                              use_existing_power=args.use_existing_power)
        log('PASS', delta_feedback_xyz_mm=delta,
            limitation='Finite displacement and cleanup confirmed; WORLD direction requires onsite observation. No automatic return.')
        return 0
    except (Exception, KeyboardInterrupt) as error:
        log('FAIL', error=str(error), raw=repr(getattr(error, 'raw', None)))
        return 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    raise SystemExit(main())
