"""Bind an original order and inspect a returned PPT without opening Office."""
import argparse
import os
from pathlib import Path
import sys

import requests

from handoff import check, inspect, json_text
from output_worker import result_for
from playback import worker_alive
from transfer import Client, load_credential, order_lock, read, write

WATCH = "return-watch.json"


def bound_order(root, thread_id):
    order = read(root / "order.json")
    check(bool(thread_id) and order.get("thread_id") == thread_id,
          "只能在订单绑定的原对话处理成品")
    check(order.get("job_id") and order.get("billing") == "settled", "需要已确认入队的原订单")
    return order


def prepare(root, thread_id):
    order = bound_order(root, thread_id)
    state_path = root / WATCH
    with order_lock(root / "return-watch.lock"):
        state = read(state_path) if state_path.exists() else {}
        check(not state or (state.get("job_id"), state.get("thread_id")) ==
              (order['job_id'], thread_id), "已有唤醒绑定属于其他订单或对话")
        state.pop('request', None)
        state.update(job_id=order['job_id'], thread_id=thread_id, wake_mode='python_receiver')
        write(state_path, state)
    return {"wake_mode": "python_receiver", "prepared": True, "receiver_started": False}


def bind(root, thread_id, automation_id):
    raise ValueError('已取消定时任务绑定；请运行 receive_and_wake.py start')


def choose(root, thread_id, record, response_source):
    order = bound_order(root, thread_id)
    check(record in {'yes', 'no'} and bool(response_source and response_source.strip()), "先收到用户的录屏选择")
    with order_lock(root / 'return-watch.lock'):
        state = read(root / WATCH)
        check(state['job_id'] == order['job_id'] and state['thread_id'] == thread_id, '唤醒绑定不匹配')
        state['recording_choice'] = {'record': record == 'yes', 'response_source': response_source}
        state.pop('recording', None)
        write(root / WATCH, state)
    return state


def recording_ready(root, thread_id, path, evidence):
    bound_order(root, thread_id)
    check(path and evidence and evidence.strip(), '需要实际录屏文件位置及已开始录制的界面证据')
    with order_lock(root / 'return-watch.lock'):
        state = read(root / WATCH)
        check(state.get('recording_choice', {}).get('record') is True, '用户尚未选择录屏')
        state['recording'] = {'path': str(Path(path).resolve()), 'started': True, 'evidence': evidence,
                              'scope': 'entire_powerpoint_window'}
        write(root / WATCH, state)
    return state


def require_output_choice(root, thread_id):
    bound_order(root, thread_id)
    state = read(root / WATCH)
    choice = state.get('recording_choice')
    check(choice and type(choice.get('record')) is bool, '请先询问用户是否录屏，收到答复后再输出')
    check(not choice['record'] or state.get('recording', {}).get('started') is True,
          '用户需要录屏，请先启动整个 PowerPoint 软件窗口的录制')


def receive_ready(client, root, order, reply):
    with order_lock(root / "result-receive.lock"):
        bundle = inspect(root, legacy=True) if 'pptx' in order.get('sha256', {}) else inspect(root)
        path = client.receive(root, order, reply, bundle)
        record = {"job_id": order['job_id'], "thread_id": order.get('thread_id'),
                  "status": "ready", "path": str(path), "sha256": reply['result']['sha256']}
        write(root / "return-ready.json", record)
    return record


def check_return(client, root, thread_id):
    order = bound_order(root, thread_id)
    path = root / 'element-playback-state.json'
    if path.exists():
        state = read(path)
        check(state.get('job_id') == order['job_id'], "输出状态属于其他订单")
        outcome = result_for(root, state)
        return {"status": outcome or ('running' if worker_alive(state.get('worker_pid')) else 'failed'),
                "job_id": order['job_id'], "path": state.get('source'),
                "diagnostic_log": str(root / 'element-playback.log')}
    reply = client.call('GET', f"/jobs/{order['job_id']}")
    check(reply.get('job_id') == order['job_id'], "服务器返回了其他订单")
    if reply['status'] == 'completed':
        ready = receive_ready(client, root, order, reply)
        watch = read(root / WATCH) if (root / WATCH).exists() else {}
        if 'recording_choice' not in watch:
            ready['status'] = 'awaiting_recording_choice'
        elif watch['recording_choice']['record'] and not watch.get('recording', {}).get('started'):
            ready['status'] = 'awaiting_recording_start'
        return ready
    check(reply['status'] in {'queued', 'processing', 'failed', 'cancelled', 'expired'}, "订单状态异常")
    return {"status": 'pending' if reply['status'] in {'queued', 'processing'} else 'failed',
            "remote_status": reply['status'], "job_id": order['job_id']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'bind', 'check', 'choose', 'recording-ready'])
    parser.add_argument('root', type=Path)
    parser.add_argument('--thread-id', default=os.environ.get('CODEX_THREAD_ID'))
    parser.add_argument('--automation-id')
    parser.add_argument('--record', choices=['yes', 'no'])
    parser.add_argument('--response-source')
    parser.add_argument('--recording-path')
    parser.add_argument('--evidence')
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.action == 'prepare':
            result = prepare(root, args.thread_id)
        elif args.action == 'bind':
            result = bind(root, args.thread_id, args.automation_id)
        elif args.action == 'choose':
            result = choose(root, args.thread_id, args.record, args.response_source)
        elif args.action == 'recording-ready':
            result = recording_ready(root, args.thread_id, args.recording_path, args.evidence)
        else:
            with requests.Session() as session:
                result = check_return(Client(session, load_credential()), root, args.thread_id)
        print(json_text(result))
        return 0
    except (OSError, ValueError, KeyError, requests.RequestException) as error:
        print(json_text({'status': 'error', 'error': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
