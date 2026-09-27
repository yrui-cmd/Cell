"""Small subprocess MCP client used by integration tests and reproducible benchmarks."""
import json
import subprocess
import queue
import threading
import time

class Client:
    def __init__(self, command, cwd=None, stderr_path=None):
        self.stderr_file = open(stderr_path, "w", encoding="utf-8") if stderr_path else subprocess.DEVNULL
        self.process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.stderr_file, text=True, encoding="utf-8", bufsize=1,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.messages = queue.Queue()
        self.counter = 0
        def reader():
            for line in self.process.stdout:
                try:
                    self.messages.put(json.loads(line))
                except ValueError:
                    self.messages.put({"invalid_stdout": line})
            self.messages.put({"eof": True})
        self.thread = threading.Thread(target=reader, daemon=True)
        self.thread.start()
        self.initialize = self.request("initialize", {"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"ppt-turbo-verifier","version":"1.0.0"}})
        self.notify("notifications/initialized", {})

    def notify(self, method, params):
        self.process.stdin.write(json.dumps({"jsonrpc":"2.0","method":method,"params":params})+"\n")
        self.process.stdin.flush()

    def request(self, method, params=None, timeout=240):
        self.counter += 1
        target_id = self.counter
        self.process.stdin.write(json.dumps({"jsonrpc":"2.0","id":target_id,"method":method,"params":params or {}},ensure_ascii=False)+"\n")
        self.process.stdin.flush()
        deadline = time.monotonic()+timeout
        while True:
            message = self.messages.get(timeout=max(0.01, deadline-time.monotonic()))
            if "eof" in message or "invalid_stdout" in message:
                raise RuntimeError(message)
            if message.get("id") == target_id:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message["result"]

    def call(self, name, arguments=None, allow_error=False):
        result = self.request("tools/call", {"name":name,"arguments":arguments or {}})
        if result.get("isError") and not allow_error:
            raise RuntimeError(result)
        data = result.get("structuredContent")
        if data is None:
            texts = [c["text"] for c in result.get("content", []) if c["type"] == "text"]
            data = json.loads(texts[0]) if texts else {}
        return data

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
        self.process.stdout.close()
        if self.stderr_file != subprocess.DEVNULL:
            self.stderr_file.close()
