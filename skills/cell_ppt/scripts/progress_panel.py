"""Serve the estimate for an existing PPT order on loopback."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.request
from zipfile import BadZipFile

import requests
from pptx.exc import PythonPptxError

from output_worker import result_for
from playback import worker_alive
from ppt_credentials import load as load_credential
from transfer import Client, MODE, check, order_lock, read, write

SECONDS_PER_CREDIT = 9 * 60 + 32
LABELS = {
    "queued": "已入队",
    "processing": "制作中",
    "completed": "制作完成 · 待领取",
    "failed": "制作失败",
    "cancelled": "订单已取消",
    "expired": "订单已过期",
}
TERMINAL = {"completed", "failed", "cancelled", "expired"}
PANEL_VERSION = 5


def load_order(root):
    path = root / "order.json"
    order = read(path)
    check(re.fullmatch(r"[0-9a-f]{32}", str(order.get("job_id", "")))
          and type(order.get("credits")) is int and order["credits"] > 0
          and order.get("status") in LABELS
          and order.get("billing") == "settled", "需要已确认入队的原 PPT 订单")
    order.setdefault("queued_at_unix", path.stat().st_mtime)
    return order


def snapshot(order, remote=None, now=None, *, output=None):
    now = time.time() if now is None else now
    estimate = order["credits"] * SECONDS_PER_CREDIT
    status = remote["status"] if remote else order["status"]
    observed = remote["checked_at"] if remote else order["queued_at_unix"]
    elapsed = max(0, (observed if status in TERMINAL else now) - order["queued_at_unix"])
    label = remote.get("playback_label", LABELS[status]) if remote else LABELS[status]
    receiving = bool(remote and remote.get("receiving"))
    if receiving:
        output = None
    elif output == "completed":
        label = "PPT 输出完成"
    elif output == "failed":
        label = "成品已保存 · 预览中断，可重试"
    return {"credits": order["credits"], "estimate_seconds": round(estimate, 1),
            "percent": 100 if status == "completed" else min(99, elapsed / estimate * 100),
            "elapsed_seconds": int(elapsed), "remaining_seconds": max(0, estimate - elapsed),
            "label": label, "terminal": status in TERMINAL and output != "running" and not receiving,
            "receiving": receiving, "output_state": output,
            "overdue": status not in TERMINAL and elapsed >= estimate,
            "source": "服务端状态" if remote else "本地订单回执"}


def refresh(server, root, order, token):
    with requests.Session() as session:
        client = Client(session, token)
        while True:
            try:
                reply = client.call("GET", f"/jobs/{order['job_id']}")
                if (reply.get("job_id") == order["job_id"] and reply.get("mode") == MODE
                        and reply.get("page_count") == order["credits"] and reply.get("status") in LABELS):
                    server.remote = {"status": reply["status"], "checked_at": time.time()}
                    if reply["status"] == "completed":
                        server.remote.update(receiving=True, playback_label="制作完成 · 正在接收成品")
                        try:
                            from return_watch import receive_ready
                            receive_ready(client, root, order, reply)
                        except requests.RequestException:
                            server.remote["playback_label"] = "制作完成 · 正在重新接收成品"
                        except (OSError, ValueError, KeyError, TypeError, BadZipFile, PythonPptxError) as error:
                            with (root / "element-playback.log").open("a", encoding="utf-8") as log:
                                log.write(f"Delivery or preview needs attention ({type(error).__name__}): {error}\n")
                            server.remote.update(receiving=False, playback_label="制作完成 · 成品接收或预览需要处理")
                            return
                        else:
                            server.remote.update(receiving=False, playback_label="成品已返回 · 等待原对话接续输出")
                            return
                    if reply["status"] in TERMINAL - {"completed"}:
                        return
            except (OSError, ValueError, requests.RequestException):
                pass
            time.sleep(60)


def make_server(order, token, root):
    prefix = "/" + token + "/"
    page = Path(__file__).with_name("progress_panel.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                self.send_error(403)
                return
            if self.path == prefix:
                body, kind = page, "text/html; charset=utf-8"
            elif self.path == prefix + "status":
                state = self.server.output
                try:
                    current = read(root / "element-playback-state.json")
                    if current.get("job_id") == order["job_id"]:
                        state = current
                except (OSError, ValueError):
                    pass
                output = None
                if state:
                    output = result_for(root, state)
                    if output is None:
                        output = "running" if worker_alive(state.get("worker_pid")) else (result_for(root, state) or "failed")
                body = json.dumps(snapshot(order, self.server.remote, output=output), ensure_ascii=False).encode()
                kind = "application/json; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.server.last_access = time.monotonic()
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.remote = None
    server.output = None
    server.last_access = time.monotonic()
    server.timeout = 1
    return server


def serve(root):
    key = load_credential()
    order = load_order(root)
    path = root / "progress-panel.json"
    meta = read(path)
    order["queued_at_unix"] = meta["queued_at_unix"]
    with make_server(order, meta["token"], root) as server:
        url = f"http://127.0.0.1:{server.server_port}/{meta['token']}/"
        write(path, {**meta, "url": url})
        threading.Thread(target=refresh, args=(server, root, order, key), daemon=True).start()
        while time.monotonic() - server.last_access < 3600:
            server.handle_request()


def alive(url):
    if not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}/[0-9a-f]{48}/", url):
        return False
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + "status", timeout=0.5) as response:
            return isinstance(json.load(response).get("estimate_seconds"), (int, float))
    except (OSError, ValueError):
        return False


def start(root):
    load_credential()
    root = Path(root).resolve()
    order = load_order(root)
    path = root / "progress-panel.json"
    with order_lock(root / "progress-panel.lock"):
        meta = read(path) if path.is_file() else {}
        if (meta.get("job_id") == order["job_id"] and alive(meta.get("url", ""))
                and meta.get("panel_version") == PANEL_VERSION):
            return meta["url"]
        queued = meta.get("queued_at_unix", order["queued_at_unix"]) if meta.get("job_id") == order["job_id"] else order["queued_at_unix"]
        write(path, {"job_id": order["job_id"], "queued_at_unix": queued,
                     "token": secrets.token_hex(24), "remote_polling": True,
                     "panel_version": PANEL_VERSION})
        exe = Path(sys.executable)
        options = {"start_new_session": True}
        if os.name == "nt":
            if exe.with_name("pythonw.exe").is_file():
                exe = exe.with_name("pythonw.exe")
            options = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
        with (root / "progress-panel.log").open("ab") as log:
            process = subprocess.Popen([str(exe), "-X", "utf8", str(Path(__file__).resolve()), str(root)],
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=log, **options)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and process.poll() is None:
            url = read(path).get("url", "")
            if alive(url):
                return url
            time.sleep(0.15)
        raise ValueError("等待面板未启动，请检查 progress-panel.log")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    serve(parser.parse_args().root)
