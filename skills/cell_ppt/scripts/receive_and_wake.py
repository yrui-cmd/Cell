"""Receive one existing paid PPT order, then wake its original chat once. No scheduler."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import requests
from return_watch import bound_order, check_return, prepare
from transfer import Client, load_credential, order_lock, read, write

STATE = 'receive-state.json'
STOP = 'receiver.stop'
SCRIPTS = Path(__file__).resolve().parent


def bridge_for(thread_id):
    from desktop_bridge import Bridge
    return Bridge(caller_thread_id=thread_id, submit_thread_ids=[thread_id], rpc_timeout=25)


def origin(bridge, thread_id):
    doc = bridge._desktop_tool('read_thread', {'threadId': thread_id, 'turnLimit': 1,
                                'includeOutputs': False, 'maxOutputCharsPerItem': 0})
    if doc.get('thread', {}).get('id') != thread_id:
        raise ValueError('Cannot verify original chat')
    return doc['thread']


def probe(thread_id):
    bridge = bridge_for(thread_id)
    try:
        origin(bridge, thread_id)
        if 'send_message_to_thread' not in bridge._available_tools:
            raise ValueError('Desktop wake tool unavailable')
        return {'desktop_reachable': True, 'thread_id': thread_id, 'sends_performed': 0}
    finally:
        bridge.close()


def bound_state(root, thread_id):
    order = bound_order(root, thread_id)
    state = read(root / STATE)
    if (state['job_id'], state['thread_id']) != (order['job_id'], thread_id):
        raise ValueError('Receiver belongs to another order/chat')
    return state


def received(root, state):
    ready = read(root / 'return-ready.json')
    if (ready['job_id'], ready['thread_id']) != (state['job_id'], state['thread_id']):
        raise ValueError('Received file belongs to another order/chat')
    path = Path(ready['path']).resolve()
    path.relative_to(root.resolve())
    if hashlib.sha256(path.read_bytes()).hexdigest() != ready['sha256']:
        raise ValueError('Received PPT checksum mismatch')
    return ready


def wake(root, state, bridge_factory=bridge_for):
    if (root / STOP).exists():
        return False
    if state['wake_state'] in {'sent', 'acknowledged', 'uncertain'}:
        return True
    if state['wake_state'] == 'sending':
        state['wake_state'] = 'uncertain'
        write(root / STATE, state)
        return True
    if state['status'] == 'ready':
        received(root, state)
    elif state['status'] != 'attention':
        raise ValueError('No verified result or actionable failure')
    bridge = bridge_factory(state['thread_id'])
    try:
        thread = origin(bridge, state['thread_id'])
        status = thread.get('status') or {}
        kind = status.get('type') if isinstance(status, dict) else status
        if kind in {'active', 'inProgress', 'running'}:
            return False
        if (root / STOP).exists():
            return False
        prompt = (f"cell_ppt Python 接收器返回原订单 {state['job_id']}，状态 {state['status']}。\n"
                  f"订单目录：{root}\n接续标记：{state['nonce']}\n"
                  f"读取 {SCRIPTS.parent / 'SKILL.md'} 和 references/return-to-chat.md。"
                  "先核对 receive-state.json、原订单和原对话，运行 receive_and_wake.py ack。"
                  "ready 时验证 return-ready.json 和 PPT 摘要，先问是否录制整个 PowerPoint 软件窗口，"
                  "等实际答复后按每 0.5 秒一个元素、自动换页输出。attention 时只报告具体问题，不输出。"
                  "仅继续本单，不重新上传、不再收费、不创建或恢复定时任务。"
                  "如果用户已要求停止，则保留文件并停止。完成记录必须匹配 job_id/run_id，"
                  "核验成品和可选录屏后才提供链接并感谢抖音：Cell-skills。")
        state['wake_state'] = 'sending'
        write(root / STATE, state)
        try:
            reply = bridge.submit(state['thread_id'], prompt)
            if not reply.get('queued') or reply.get('thread_id') != state['thread_id']:
                raise ValueError('Wake acknowledgement mismatch')
        except Exception:
            # An ambiguous acknowledgement must never trigger a blind resend.
            state['wake_state'] = 'uncertain'
            write(root / STATE, state)
            return True
        state.update(wake_state='sent', sent_at=time.time())
        write(root / STATE, state)
        return True
    finally:
        bridge.close()


def worker(root, thread_id, timeout=86400, interval=30):
    with order_lock(root / 'receiver.lock'):
        state = bound_state(root, thread_id)
        state.update(worker_pid=os.getpid(), started_at=time.time())
        write(root / STATE, state)
        deadline = time.monotonic() + timeout
        failures = 0
        with requests.Session() as session:
            client = Client(session, load_credential())
            while time.monotonic() < deadline:
                state = bound_state(root, thread_id)
                if (root / STOP).exists():
                    state['status'] = 'stopped'
                    write(root / STATE, state)
                    return
                if state['wake_state'] in {'sent', 'acknowledged', 'uncertain'}:
                    return
                try:
                    if state['status'] not in {'ready', 'attention'}:
                        result = check_return(client, root, thread_id)
                        state['last_result'] = result
                        if result['status'] in {'running', 'completed'}:
                            state['status'] = 'already_handled'
                            write(root / STATE, state)
                            return
                        if result['status'] == 'failed':
                            state['status'] = 'attention'
                        elif result['status'] != 'pending':
                            received(root, state)
                            state['status'] = 'ready'
                        write(root / STATE, state)
                    if state['status'] in {'ready', 'attention'} and wake(root, state):
                        return
                    failures = 0
                except Exception as error:
                    failures += 1
                    state['last_error'] = type(error).__name__
                    if failures >= 12:
                        state['status'] = 'attention'
                    write(root / STATE, state)
                for _ in range(interval):
                    if (root / STOP).exists():
                        break
                    time.sleep(1)
        state.update(status='attention', last_error='ReceiverTimeout')
        write(root / STATE, state)


def start(root, thread_id):
    prepare(root, thread_id)
    probe(thread_id)
    with order_lock(root / 'receiver-start.lock'):
        if (root / STOP).exists():
            raise ValueError('Receiver stopped; resume only after explicit user instruction')
        if (root / STATE).exists():
            # Repeated start is read-only; a crashed process needs explicit resume.
            return bound_state(root, thread_id)
        order = bound_order(root, thread_id)
        state = {'job_id': order['job_id'], 'thread_id': thread_id,
                 'status': 'waiting', 'wake_state': 'pending', 'nonce': uuid.uuid4().hex}
        write(root / STATE, state)
        return launch(root, thread_id)


def launch(root, thread_id):
    command = [sys.executable, str(Path(__file__).resolve()), 'worker', str(root), '--thread-id', thread_id]
    with (root / 'receiver.log').open('ab') as log:
        options = {'stdin': subprocess.DEVNULL, 'stdout': log, 'stderr': log}
        if os.name == 'nt':
            options['creationflags'] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        else:
            options['start_new_session'] = True
        process = subprocess.Popen(command, **options)
    return {'started': True, 'worker_pid': process.pid, 'state_path': str(root / STATE)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'worker', 'status', 'stop', 'resume', 'ack', 'probe'])
    parser.add_argument('root', type=Path)
    parser.add_argument('--thread-id', default=os.environ.get('CODEX_THREAD_ID'))
    parser.add_argument('--nonce')
    args = parser.parse_args()
    root = args.root.resolve()
    bound_order(root, args.thread_id)
    if args.action == 'probe':
        result = probe(args.thread_id)
    elif args.action == 'start':
        result = start(root, args.thread_id)
    elif args.action == 'worker':
        worker(root, args.thread_id)
        return
    else:
        state = bound_state(root, args.thread_id)
        if args.action == 'stop':
            (root / STOP).touch()
        elif args.action == 'ack':
            if args.nonce != state['nonce'] or state['wake_state'] not in {'sending', 'sent', 'uncertain', 'acknowledged'}:
                raise ValueError('Wake acknowledgement does not match')
            with order_lock(root / 'receiver.lock'):
                state = bound_state(root, args.thread_id)
                state['wake_state'] = 'acknowledged'
                write(root / STATE, state)
        elif args.action == 'resume':
            probe(args.thread_id)
            with order_lock(root / 'receiver.lock'):
                state = bound_state(root, args.thread_id)
                if state['wake_state'] != 'pending':
                    raise ValueError('Wake already sent or uncertain; reconcile in original chat')
                (root / STOP).unlink(missing_ok=True)
                state['status'] = 'waiting'
                write(root / STATE, state)
            result = launch(root, args.thread_id)
            print(result)
            return
        result = state
    from handoff import json_text
    print(json_text(result))


if __name__ == '__main__':
    main()
