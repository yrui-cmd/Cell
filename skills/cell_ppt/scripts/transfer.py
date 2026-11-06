"""Quote and confirm an approved handoff against the fixed PPT service."""
import argparse
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import sys
from tempfile import NamedTemporaryFile
import time
import uuid

import requests

from handoff import MATERIAL, PLAN, TEMPLATE, check, inspect, json_text, sha, slide_count
from ppt_credentials import API, load as load_credential

MODE = "planned_deck"
FINAL_PPTX = "成品.pptx"
NAMES = {"pptx": PLAN, "pptx2": TEMPLATE, "material": MATERIAL}
FILE_TYPES = {"pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
              "pdf": "application/pdf"}


def write(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json_text(data), encoding="utf-8")
    tmp.replace(path)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


@contextmanager
def order_lock(path):
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


class Client:
    def __init__(self, session, token):
        self.session, self.token = session, token

    def call(self, method, route, *, public=False, headers=None, **payload):
        headers = dict(headers or {})
        if not public:
            headers["Authorization"] = f"Bearer {self.token}"
        response = self.session.request(method, API + route, headers=headers,
                                        timeout=(10, 120), allow_redirects=False, **payload)
        if not 200 <= response.status_code < 300:
            raise ValueError(f"PPT 接口 {route} 返回 HTTP {response.status_code}")
        return response.json()

    def verify_quote(self, quote, bundle):
        price = quote["price"]
        check(quote.get("mode") == MODE and quote["page_count"] == bundle["credits"]
              and price == {"amount": bundle["credits"], "unit": "ppt_page_credit"},
              "服务器订单模式、页数或报价与已确认版本不符，未扣费")
        check({role: item["sha256"] for role, item in quote["files"].items()} == bundle["sha256"],
              "服务器文件摘要与已确认版本不符，未扣费")
        if "pptx" in bundle["sha256"]:
            check(quote["files"]["pptx"]["page_count"] == bundle["plan_pages"]
                  and quote["files"].get("pptx2", {}).get("page_count", 0) == bundle["template_pages"],
                  "服务器单文件页数不符，未扣费")

    def submit(self, root, approval):
        root = Path(root)
        state_path = root / "order.json"
        existing = read(state_path) if state_path.exists() else {}
        legacy_order = bool(existing.get("job_id") and "pptx" in existing.get("sha256", {}))
        bundle = inspect(root, legacy=True) if legacy_order else inspect(root)
        check(existing.get("job_id") or bundle.get("upload_format") == "single_pdf",
              "新订单仅支持单 PDF；请重新生成含 ppt-material-index.json 的交接 PDF，并确认新摘要和额度")
        check(approval.get("approved") is True and approval.get("sha256") == bundle["sha256"]
              and approval.get("credits") == bundle["credits"] and approval.get("thread_id")
              and approval.get("customer_confirmation"), "需要当前文件和额度的客户确认")
        state_path = root / "order.json"
        with order_lock(root / "order.lock"):
            state = read(state_path) if state_path.exists() else {
                "idempotency_key": uuid.uuid4().hex, "sha256": bundle["sha256"],
                "credits": bundle["credits"], "thread_id": approval["thread_id"]}
            check(state["sha256"] == bundle["sha256"] and state["credits"] == bundle["credits"]
                  and state["thread_id"] == approval["thread_id"], "已存在不同版本订单，请使用新交接目录")
            if state.get("billing") == "settled" and "queued_at_unix" not in state:
                state["queued_at_unix"] = state_path.stat().st_mtime
            write(state_path, state)
            if not state.get("job_id"):
                health = self.call("GET", "/health", public=True)
                check(health.get("ok") is True and MODE in health.get("job_modes", []),
                      "现网尚未公布 planned_deck，保留交接包，未上传")
                contract = health.get("planned_upload", {})
                check(health.get("version") == 2 and contract.get("files") == ["material"]
                      and contract.get("format") == "pdf" and contract.get("billing") == "declared_ppt_content_pages",
                      "服务未声明受支持的单 PDF 契约，未上传")
                check(set(bundle["sha256"]) == {"material"}, "新订单仅允许上传交接 PDF")
                balance = self.call("GET", "/balance")
                check(balance["available_pages"] >= bundle["credits"], "PPT 页额度不足")
                with ExitStack() as stack:
                    parts = {}
                    for role in bundle["sha256"]:
                        path = root / NAMES[role]
                        stream = stack.enter_context(path.open("rb"))
                        parts[role] = (path.name, stream, FILE_TYPES[path.suffix[1:]])
                    quote = self.call("POST", "/uploads", files=parts,
                                      headers={"Idempotency-Key": state["idempotency_key"], "X-PPT-Job-Mode": MODE})
                self.verify_quote(quote, bundle)
                job = quote["job_id"]
                check(isinstance(job, str) and len(job) == 32
                      and all(ch in "0123456789abcdef" for ch in job), "订单号格式异常")
                state["job_id"] = job
                write(state_path, state)
            route = f"/jobs/{state['job_id']}"
            status = self.call("GET", route)
            self.verify_quote(status, bundle)
            if status["status"] == "quoted":
                status = self.call("POST", route + "/confirm",
                                   json={"expected_page_credits": bundle["credits"]})
            state["status"] = status["status"]
            state["billing"] = status["billing"]
            if state["billing"] == "settled":
                state.setdefault("queued_at_unix", time.time())
            write(state_path, state)
            return state


    def receive(self, root, order, reply, bundle):
        self.verify_quote(reply, bundle)
        check(reply["job_id"] == order["job_id"] and reply["status"] == "completed"
              and reply["billing"] == "settled", "等待原订单成品回传")
        result = reply["result"]
        digest, size = result["sha256"], result["bytes"]
        result_pages = result.get("page_count")
        check(type(result_pages) is int and 1 <= result_pages <= 500
              and ("pptx" not in bundle["sha256"] or result_pages == bundle["plan_pages"])
              and isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
              and type(size) is int and 0 < size <= 512 * 1024**2, "回传成品的页数或文件信息不符")
        destination = root / "交付" / FINAL_PPTX
        destination.parent.mkdir(exist_ok=True)
        if destination.exists():
            check(destination.stat().st_size == size and sha(destination) == digest
                  and slide_count(destination) == result_pages, "已保存的回传原件与服务端成品不符")
            return destination

        legacy = next((path for path in (root / "交付" / "成品ppt.pptx",
                                        root / "成品_回传原件.pptx") if path.is_file()), None)
        with NamedTemporaryFile(dir=destination.parent, suffix=".pptx", delete=False) as stream:
            staged = Path(stream.name)
        try:
            if legacy is not None:
                check(legacy.stat().st_size == size, "已保存的回传原件与服务端成品不符")
                shutil.copyfile(legacy, staged)
            else:
                url = f"{API}/jobs/{order['job_id']}/result"
                received = 0
                with self.session.get(url, headers={"Authorization": f"Bearer {self.token}"},
                                      stream=True, timeout=(10, 120), allow_redirects=False) as response:
                    check(response.status_code == 200, f"成品下载返回 HTTP {response.status_code}")
                    with staged.open("wb") as stream:
                        for chunk in response.iter_content(1024 * 1024):
                            received += len(chunk)
                            check(received <= size, "回传成品超出回执大小")
                            stream.write(chunk)
            check(staged.stat().st_size == size and sha(staged) == digest
                  and slide_count(staged) == result_pages, "回传成品的摘要或页数验证失败")
            staged.rename(destination)
        finally:
            staged.unlink(missing_ok=True)
        return destination


def play_elements(client, root, order, reply):
    from playback import launch, prepare, worker_alive
    from output_worker import result_for

    with order_lock(root / "playback.lock"):
        state_path = root / "element-playback-state.json"
        state = read(state_path) if state_path.is_file() else {}
        if state:
            check(state.get("job_id") == order["job_id"], "已有预览属于其他订单")
            outcome = result_for(root, state)
            if outcome == "completed" or (outcome is None and worker_alive(state.get("worker_pid"))):
                return state
            # A failed or exited worker is retryable. Preserve the old preview and rebuild.
            state = {}
        if not state:
            source = client.receive(root, order, reply,
                                    inspect(root, legacy=True) if "pptx" in order.get("sha256", {}) else inspect(root))
            copy = root / FINAL_PPTX
            macos = sys.platform == "darwin"
            if macos or copy.exists():
                copy = root / f"成品_输出预览_{uuid.uuid4().hex[:8]}.pptx"
            targets = prepare(source, copy, macos=macos)
            state = {"job_id": order["job_id"], "copy_sha256": sha(copy),
                     "source": str(source.resolve()), "copy": str(copy.resolve()), "targets": targets}
        copy = Path(state["copy"])
        check(state["job_id"] == order["job_id"] and copy.parent == root.resolve()
              and state["copy_sha256"] == sha(copy), "已有输出预览副本与原订单不一致")
        state["run_id"] = uuid.uuid4().hex
        write(state_path, state)
        state["worker_pid"] = launch(state_path)
        write(state_path, state)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["submit", "status", "progress", "play-elements"])
    parser.add_argument("root", type=Path)
    # Older launchers pass this flag. Playback is now the default.
    parser.add_argument("--play-elements-on-return", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.action == "progress":
            from progress_panel import start
            print(json_text({"progress_url": start(args.root),
                             "remote_polling": True}))
            return 0
        token = load_credential()
        with requests.Session() as session:
            client = Client(session, token)
            if args.action == "submit":
                state = client.submit(args.root, read(args.root / "approval.json"))
            elif args.action == "play-elements":
                from progress_panel import load_order
                order = load_order(args.root)
                reply = client.call("GET", f"/jobs/{order['job_id']}")
                state = play_elements(client, args.root, order, reply)
            else:
                order = read(args.root / "order.json")
                state = client.call("GET", f"/jobs/{order['job_id']}")
        print(json_text(state))
        return 0
    except (OSError, ValueError, KeyError, requests.RequestException) as error:
        print(json_text({"error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

