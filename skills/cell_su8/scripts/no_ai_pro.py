#!/usr/bin/env python3
"""Customer-only no-ai-pro client; one submission, durable resume, verified PNG.

Neither this client nor a successful download certifies removal of an invisible
watermark. No worker credentials are accepted.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import io
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from update_gate import enforce_latest, UpdateGateError

ORIGIN = "https://xiaomiao-ai.com"
PREFIX = "/api/no-ai-pro-jobs"
TOKEN = re.compile(r"img_live_[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\Z")
JOB_ID = re.compile(r"wm_[0-9a-f]{20}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
JSON_LIMIT = 1024 * 1024
INPUT_LIMIT = 32 * 1024 * 1024
RESULT_LIMIT = 64 * 1024 * 1024
RECOGNITION_LIMIT = 10 * 1024 * 1024
PIXEL_LIMIT = 40_000_000
COST = 3


class ClientError(RuntimeError):
    """A safe error message; never include credentials or server response bodies."""


class NetworkError(ClientError):
    pass


@dataclass
class Response:
    status: int
    body: bytes
    headers: dict


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpTransport:
    """Fixed HTTPS origin. Redirects and POST retries are deliberately disabled."""

    def __init__(self):
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, path, *, token=None, data=None, content_type=None,
                limit=JSON_LIMIT, timeout=30, deadline=None):
        if not re.fullmatch(
            r"/api/(?:balance|no-ai-pro-jobs(?:/health|/wm_[0-9a-f]{20}(?:/result)?)?)", path
        ) or method not in {"GET", "POST"}:
            raise ClientError("Unsupported customer route or method.")
        headers = {"Accept": "application/json" if limit == JSON_LIMIT else "image/png"}
        if token is not None:
            if not TOKEN.fullmatch(token):
                raise ClientError("A customer img_live API key is required.")
            headers["Authorization"] = "Bearer " + token
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(ORIGIN + path, data=data, headers=headers, method=method)
        try:
            try:
                response = self.opener.open(request, timeout=timeout)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                length = response.headers.get("Content-Length")
                if length is not None and (not length.isdigit() or int(length) > limit):
                    raise ClientError("Response exceeds the allowed size.")
                chunks, total = [], 0
                while True:
                    if deadline is not None and time.monotonic() >= deadline:
                        raise NetworkError("Request wait budget elapsed; resume the existing task.")
                    chunk = response.read(min(1024 * 1024, limit + 1 - total))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        raise ClientError("Response exceeds the allowed size.")
                    chunks.append(chunk)
                body = b"".join(chunks)
                return Response(response.status, body, dict(response.headers.items()))
        except (OSError, urllib.error.URLError) as error:
            raise NetworkError("Network request failed; use the same task directory to resume.") from None


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def sync_directory(path):
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".part")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def job_lock(directory):
    """OS-owned lock survives stale lock files but never concurrent writers."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    sync_directory(directory.parent)
    with (directory / ".client.lock").open("a+b") as lock:
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ClientError("Another client is already using this task directory.") from None
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def image_info(data, *, png_only=False):
    try:
        from PIL import Image
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                allowed = {"PNG"} if png_only else {"PNG", "JPEG", "WEBP"}
                if image.format not in allowed or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("format or frame count")
                width, height = image.size
                if width < 1 or height < 1 or width * height > PIXEL_LIMIT:
                    raise ValueError("pixel limit")
                fmt = image.format
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                orientation = image.getexif().get(274, 1)
                image.load()
        if png_only and orientation not in {None, 1}:
            raise ValueError("returned orientation must be baked into pixels")
        visible = [height, width] if orientation in {5, 6, 7, 8} else [width, height]
        return {"format": fmt, "raw_canvas_px": [width, height], "canvas_px": visible,
                "mime": {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[fmt]}
    except ImportError:
        raise ClientError("Pillow is required to decode and verify images.") from None
    except Exception:
        raise ClientError("Invalid image: use a single-frame PNG, JPEG or WebP, at most 40 MP.") from None


def read_input(path):
    path = Path(path).expanduser().resolve(strict=True)
    if not path.is_file() or not 0 < path.stat().st_size <= INPUT_LIMIT:
        raise ClientError("Input image must be between 1 byte and 32 MiB.")
    data = path.read_bytes()
    if len(data) > INPUT_LIMIT:
        raise ClientError("Input image exceeds 32 MiB.")
    info = image_info(data)
    return path, data, info


def get_token():
    """Reuse the current account's protected customer key, never copy or log it."""
    system = platform.system()
    if system == "Windows":
        secret = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".codex/secrets/xiaomiao-api-key.dpapi"
        try:
            encrypted = bytes.fromhex(secret.read_text(encoding="utf-8-sig").strip())
        except (OSError, ValueError):
            raise ClientError("The current Windows account has no usable protected Xiaomiao customer key.") from None
        class Blob(ctypes.Structure):
            _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]
        buffer = (ctypes.c_ubyte * len(encrypted)).from_buffer_copy(encrypted)
        incoming = Blob(len(encrypted), buffer)
        outgoing = Blob()
        crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(Blob)]
        crypt.CryptUnprotectData.restype = ctypes.c_int
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        if not crypt.CryptUnprotectData(ctypes.byref(incoming), None, None, None, None,
                                       1, ctypes.byref(outgoing)):
            raise ClientError("Windows DPAPI could not unlock the customer key for this account.")
        try:
            try:
                token = ctypes.string_at(outgoing.data, outgoing.size).decode("utf-16-le").strip()
            except UnicodeError:
                raise ClientError("The protected customer key could not be decoded.") from None
        finally:
            ctypes.memset(outgoing.data, 0, outgoing.size)
            kernel.LocalFree(outgoing.data)
    elif system == "Darwin":
        account = subprocess.run(["id", "-un"], check=True, capture_output=True, text=True).stdout.strip()
        result = subprocess.run(["security", "find-generic-password", "-s", "cell-ppt-xiaomiao",
            "-a", account, "-w"], check=False, capture_output=True, text=True)
        if result.returncode:
            raise ClientError("The current macOS account has no Xiaomiao customer key in Keychain.")
        token = result.stdout.strip()
    else:
        raise ClientError("Protected customer credentials are supported on Windows and macOS.")
    if not TOKEN.fullmatch(token):
        token = ""
        raise ClientError("The protected value is not a customer img_live API key; worker keys are forbidden.")
    return token


def json_body(response):
    if len(response.body) > JSON_LIMIT:
        raise ClientError("JSON response exceeds the allowed size.")
    try:
        value = json.loads(response.body.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise ClientError("The server did not return a valid JSON object.") from None
    if not isinstance(value, dict):
        raise ClientError("The server did not return a JSON object.")
    return value


class Client:
    def __init__(self, token=None, *, transport=None, sleep=time.sleep, monotonic=time.monotonic,
                 stderr=None):
        if token is not None and not TOKEN.fullmatch(token):
            raise ClientError("A customer img_live API key is required; worker tokens are forbidden.")
        self.token = token
        self.transport = transport or HttpTransport()
        self.sleep = sleep
        self.monotonic = monotonic
        self.stderr = stderr if stderr is not None else sys.stderr

    def request(self, method, path, *, data=None, content_type=None, limit=JSON_LIMIT,
                authenticated=True, deadline=None):
        if authenticated and not self.token:
            raise ClientError("A protected customer API key is required.")
        # Only idempotent GET is retried, at most three attempts total.
        for attempt in range(3 if method == "GET" else 1):
            remaining = 30 if deadline is None else deadline - self.monotonic()
            if remaining <= 0:
                raise NetworkError("Request wait budget elapsed; resume the existing task.")
            try:
                response = self.transport.request(method, path, token=self.token if authenticated else None,
                    data=data, content_type=content_type, limit=limit, timeout=min(30, remaining), deadline=deadline)
            except NetworkError:
                if method == "GET" and attempt < 2:
                    self.sleep(min(1, max(0, deadline - self.monotonic())) if deadline is not None else 1)
                    continue
                raise
            if method == "GET" and response.status in {408, 429, 500, 502, 503, 504} and attempt < 2:
                self.sleep(min(1, max(0, deadline - self.monotonic())) if deadline is not None else 1)
                continue
            return response
        raise ClientError("GET retry limit reached.")

    def health(self):
        response = self.request("GET", PREFIX + "/health", authenticated=False)
        value = json_body(response)
        if response.status != 200 or value.get("ok") is not True:
            raise ClientError("Pro health check failed (HTTP %s)." % response.status)
        return {"ok": True, "http_status": response.status, "service": value.get("service"),
                "cost_per_image": value.get("cost_per_image")}

    def balance(self, *, deadline=None):
        response = self.request("GET", "/api/balance", deadline=deadline)
        value = json_body(response)
        available = value.get("available_credits")
        if (response.status != 200 or value.get("ok") is not True or
            isinstance(available, bool) or not isinstance(available, (int, float)) or
            (isinstance(available, float) and not math.isfinite(available)) or available < 0):
            raise ClientError("A fresh HTTP 200 balance with valid available_credits is required.")
        return {"ok": True, "available_credits": available, "checked_at": now()}

    def process(self, image, directory, *, approved_three_credits=False,
                approved_one_credit=False, approved_five_credits=False, wait_seconds=900):
        self.valid_wait(wait_seconds)
        directory = Path(directory).expanduser().resolve()
        with job_lock(directory):
            if (directory / "state.json").exists():
                state = self.load_state(directory)
                if Path(image).expanduser().resolve() != Path(state["source_path"]):
                    raise ClientError("This task directory is bound to a different input; resume the existing task.")
                return self._resume(directory, state, wait_seconds)
            # An orphan result must never be overwritten or bound to a new charge.
            if (directory / "result.png").exists() or (directory / "result_receipt.json").exists():
                raise ClientError("Task directory contains an unbound result; choose a new empty directory.")
            if not approved_three_credits:
                if approved_one_credit or approved_five_credits:
                    obsolete = "--approved-one-credit" if approved_one_credit else "--approved-five-credits"
                    raise ClientError("Pro now costs 3 credits; %s cannot authorize a new submission. Use --approved-three-credits after showing the current cost." % obsolete)
                raise ClientError("New submission requires --approved-three-credits after showing the 3-credit cost.")
            path, data, info = read_input(image)
            balance = self.balance()
            print("实时可用余额：%s；本次费用：3 额度（上传预留，首次下载结算）。" % balance["available_credits"],
                  file=self.stderr, flush=True)
            if balance["available_credits"] < COST:
                raise ClientError("At least 3 available credits are required; no image was submitted.")
            state = {"schema_version": 1, "service": "no-ai-pro", "origin": ORIGIN, "api_prefix": PREFIX,
                "source_path": str(path), "source_sha256": digest(data), "source_bytes": len(data),
                "canvas_px": info["canvas_px"], "source_file_canvas_px": info["raw_canvas_px"],
                "created_at": now(), "balance_before": balance, "cost": COST,
                "authorized_cost": COST, "approved_three_credits": True,
                "post_attempts": 1, "status": "submission_uncertain",
                "job_id": None, "note": "Submission barrier saved before POST; never submit this task again."}
            # Flush the barrier before any possibility of sending the request.
            self.save(directory, state)
            if file_digest(path) != state["source_sha256"]:
                state["status"] = "input_changed_before_submission"
                self.save(directory, state)
                raise ClientError("Input changed before submission; no request was sent.")
            boundary = "cell-su8-" + uuid.uuid4().hex
            # A fixed ASCII filename cannot inject multipart fields or headers.
            suffix = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[info["format"]]
            payload = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="reference.{suffix}"\r\n'
                       f'Content-Type: {info["mime"]}\r\n\r\n').encode() + data + f"\r\n--{boundary}--\r\n".encode()
            try:
                response = self.request("POST", PREFIX, data=payload,
                    content_type="multipart/form-data; boundary=" + boundary)
                value = json_body(response)
            except ClientError:
                state["last_error"] = "Submission response unavailable or invalid; no automatic resubmission."
                self.save(directory, state)
                return self.summary(directory, state)
            candidate = value.get("job_id")
            if isinstance(candidate, str) and JOB_ID.fullmatch(candidate):
                state["job_id"] = candidate
                state["status"] = "submitted"
                self.save(directory, state)  # Persist the known id before all other response checks.
            state["submission_http_status"] = response.status
            if "cost" in value:
                reported_cost = value["cost"]
                state["submission_reported_cost"] = reported_cost
                if self.valid_cost(reported_cost):
                    state["cost"] = reported_cost  # Actual job price, not the new default.
                if not self.valid_cost(reported_cost) or reported_cost != COST:
                    state["last_error"] = "Server submission cost differs from the authorized 3 credits; retain this job for manual reconciliation and never resubmit."
                    if state["job_id"]:
                        state["status"] = "pricing_mismatch"
                    self.save(directory, state)
                    return self.summary(directory, state)
            if not state["job_id"]:
                state["status"] = ("submission_rejected" if 400 <= response.status < 500 and
                                   value.get("ok") is False else "submission_uncertain")
                self.save(directory, state)
                return self.summary(directory, state)
            return self._wait(directory, state, wait_seconds)

    def resume(self, directory, *, wait_seconds=900):
        self.valid_wait(wait_seconds)
        directory = Path(directory).expanduser().resolve()
        with job_lock(directory):
            return self._resume(directory, self.load_state(directory), wait_seconds)

    def load_state(self, directory):
        try:
            path = directory / "state.json"
            if path.stat().st_size > JSON_LIMIT:
                raise ValueError()
            state = json.loads(path.read_text(encoding="utf-8"))
            if (state.get("schema_version") != 1 or state.get("origin") != ORIGIN or
                state.get("api_prefix") != PREFIX or state.get("service") != "no-ai-pro" or
                not isinstance(state.get("source_path"), str) or
                not isinstance(state.get("status"), str) or
                not SHA256.fullmatch(state.get("source_sha256", "")) or
                not self.valid_canvas(state.get("canvas_px"))):
                raise ValueError()
            if state.get("job_id") is not None and not JOB_ID.fullmatch(state["job_id"]):
                raise ValueError()
            return state
        except (OSError, ValueError, TypeError, AttributeError):
            raise ClientError("Missing or invalid task state; never recreate a lost submission automatically.") from None

    @staticmethod
    def valid_cost(value):
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    @staticmethod
    def valid_canvas(value):
        return (isinstance(value, list) and len(value) == 2 and
                all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value) and
                value[0] * value[1] <= PIXEL_LIMIT)

    def save(self, directory, state):
        state["updated_at"] = now()
        atomic_json(directory / "state.json", state)

    def _resume(self, directory, state, wait_seconds):
        if state["status"] == "completed":
            target = directory / "result.png"
            if (not target.is_file() or not 0 < target.stat().st_size <= RESULT_LIMIT or
                file_digest(target) != state.get("result_sha256")):
                raise ClientError("Saved result is missing or changed; do not replace it automatically.")
            self.verify_png(target.read_bytes(), state, state["result_sha256"])
            self.assert_original(state)
            if not (directory / "result_receipt.json").exists():
                self.write_receipt(directory, state)
            return self.summary(directory, state)
        # A crash after the atomic PNG publication can be recovered from the
        # already verified remote SHA, even after the short result TTL elapses.
        if (state.get("status") == "downloading" and (directory / "result.png").is_file() and
            isinstance(state.get("expected_result_sha256"), str) and
            SHA256.fullmatch(state["expected_result_sha256"])):
            expected = state["expected_result_sha256"]
            if not 0 < (directory / "result.png").stat().st_size <= RESULT_LIMIT:
                raise ClientError("Saved result exceeds the allowed size.")
            data = (directory / "result.png").read_bytes()
            self.verify_png(data, state, expected)
            return self.finish(directory, state, data, expected)
        if not state.get("job_id") or state["status"] in {"failed", "cancelled", "expired", "not_found", "pricing_mismatch"}:
            return self.summary(directory, state)
        return self._wait(directory, state, wait_seconds)

    def _wait(self, directory, state, wait_seconds):
        self.valid_wait(wait_seconds)
        deadline = self.monotonic() + wait_seconds
        while True:
            try:
                response = self.request("GET", PREFIX + "/" + state["job_id"],
                                        deadline=deadline if wait_seconds > 0 else None)
                if response.status in {404, 410}:
                    state["status"] = "not_found" if response.status == 404 else "expired"
                    state["last_http_status"] = response.status
                    self.save(directory, state)
                    return self.summary(directory, state)
                value = json_body(response)
                if response.status != 200 or value.get("ok") is not True:
                    raise ClientError("Status request failed (HTTP %s); resume this task later." % response.status)
                if value.get("job_id") != state["job_id"]:
                    raise ClientError("Status response refers to a different task.")
                if value.get("source_sha256") != state["source_sha256"] or value.get("canvas_px") != state["canvas_px"]:
                    raise ClientError("Status response does not match the original image identity and canvas.")
                if "cost" in value:
                    state["status_reported_cost"] = value["cost"]
                    if not self.valid_cost(value["cost"]) or value["cost"] != state.get("cost"):
                        state["status"] = "pricing_mismatch"
                        raise ClientError("Server status cost differs from this task's frozen price; retain the original job and never resubmit.")
                status = value.get("status")
                if not isinstance(status, str) or len(status) > 80:
                    raise ClientError("Invalid remote task status.")
                state["remote_status"] = status
                expiry = value.get("expires_at")
                if expiry is not None and (not isinstance(expiry, str) or len(expiry) > 80):
                    raise ClientError("Invalid task expiry in the status response.")
                state["expires_at"] = expiry
                state["status_checked_at"] = now()
                state.pop("last_error", None)
                if status in {"failed", "cancelled", "expired"}:
                    state["status"] = status
                    self.save(directory, state)
                    return self.summary(directory, state)
                if status == "completed":
                    expected = value.get("result_sha256")
                    if not isinstance(expected, str) or not SHA256.fullmatch(expected):
                        raise ClientError("Completed task is missing an actual result_sha256; no result accepted.")
                    state["expected_result_sha256"] = expected
                    state["status"] = "downloading"
                    self.save(directory, state)
                    return self._download(directory, state, expected,
                                          deadline=deadline if wait_seconds > 0 else None)
                if status not in {"received", "processing"}:
                    state["status"] = "unknown_status"
                    self.save(directory, state)
                    return self.summary(directory, state)
                state["status"] = status
                self.save(directory, state)
            except ClientError as error:
                state["last_error"] = str(error)
                self.save(directory, state)
                return self.summary(directory, state)
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                state["wait_timed_out"] = True
                self.save(directory, state)
                return self.summary(directory, state)
            self.sleep(min(5, remaining))

    def verify_png(self, data, state, expected):
        if not 0 < len(data) <= RESULT_LIMIT or digest(data) != expected:
            raise ClientError("Downloaded result SHA-256 does not match the task status.")
        info = image_info(data, png_only=True)
        if info["canvas_px"] != state["canvas_px"]:
            raise ClientError("Returned PNG dimensions differ from the input visible dimensions.")
        return info

    @staticmethod
    def valid_wait(value):
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            not math.isfinite(value) or not 0 <= value <= 900):
            raise ClientError("wait_seconds must be between 0 and 900.")

    @staticmethod
    def assert_original(state):
        original = Path(state["source_path"])
        if not original.is_file() or file_digest(original) != state["source_sha256"]:
            raise ClientError("Original input is missing or changed; downloaded PNG was not accepted.")

    def _download(self, directory, state, expected, *, deadline=None):
        target = directory / "result.png"
        if target.exists():
            if not 0 < target.stat().st_size <= RESULT_LIMIT:
                raise ClientError("Saved result exceeds the allowed size.")
            data = target.read_bytes()
            self.verify_png(data, state, expected)
        else:
            response = self.request("GET", PREFIX + "/" + state["job_id"] + "/result",
                                    limit=RESULT_LIMIT, deadline=deadline)
            state["result_download_http_status"] = response.status
            headers = {k.lower(): v for k, v in response.headers.items()}
            state["download_charged_header"] = headers.get("x-xiaomiao-charged")
            state["download_expires_header"] = headers.get("x-xiaomiao-expires-at")
            self.save(directory, state)  # Retain the actual billing header even if PNG verification fails.
            if response.status != 200:
                raise ClientError("Result download failed (HTTP %s); resume this task later." % response.status)
            data = response.body
            self.verify_png(data, state, expected)
            if headers.get("x-content-sha256") not in {None, expected}:
                raise ClientError("Result header and task SHA-256 disagree.")
            self.assert_original(state)
            temporary = target.with_name("result." + uuid.uuid4().hex + ".part")
            try:
                with temporary.open("xb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                # Hard-link publishes a complete file without replacing an existing result.
                try:
                    os.link(temporary, target)
                    sync_directory(directory)
                except FileExistsError:
                    if file_digest(target) != expected:
                        raise ClientError("A different result.png already exists; it was not overwritten.")
            finally:
                temporary.unlink(missing_ok=True)
        return self.finish(directory, state, data, expected, deadline=deadline)

    def finish(self, directory, state, data, expected, *, deadline=None):
        self.assert_original(state)
        try:
            balance_after = self.balance(deadline=deadline)
        except ClientError:
            balance_after = None
        state.update({"status": "completed", "completed_at": now(), "result_sha256": expected,
            "result_bytes": len(data), "result_canvas_px": state["canvas_px"],
            "recognition_compatible": len(data) <= RECOGNITION_LIMIT, "balance_after": balance_after,
            "original_unchanged": file_digest(state["source_path"]) == state["source_sha256"],
            "visual_review": "not_performed_by_client", "hidden_watermark_removal_verified": False})
        state.pop("last_error", None)
        state.pop("wait_timed_out", None)
        self.save(directory, state)
        self.write_receipt(directory, state)
        return self.summary(directory, state)

    def write_receipt(self, directory, state):
        receipt = {k: state.get(k) for k in ("service", "job_id", "source_path", "source_sha256", "canvas_px",
            "cost", "authorized_cost", "submission_reported_cost", "status_reported_cost",
            "source_file_canvas_px", "result_sha256", "result_bytes", "result_canvas_px", "recognition_compatible",
            "download_charged_header", "download_expires_header", "balance_before", "balance_after",
            "original_unchanged", "visual_review", "hidden_watermark_removal_verified", "completed_at")}
        receipt["output_path"] = str(directory / "result.png")
        receipt["limitations"] = self.limitations(state)
        atomic_json(directory / "result_receipt.json", receipt)

    @staticmethod
    def limitations(state):
        result = ["A successful Pro response/download does not verify removal of invisible watermarks."]
        if state.get("recognition_compatible") is False:
            result.append("Result exceeds the downstream path-recognition 10 MiB limit; do not auto-compress, resize or regenerate.")
        return result

    def summary(self, directory, state):
        completed = state["status"] == "completed"
        terminal = state["status"] in {"failed", "cancelled", "expired", "not_found", "submission_rejected",
                                      "input_changed_before_submission", "pricing_mismatch"}
        return {"ok": completed, "status": state["status"], "job_id": state.get("job_id"),
            "job_dir": str(directory), "state_path": str(directory / "state.json"),
            "output_path": str(directory / "result.png") if completed else None,
            "result_sha256": state.get("result_sha256"), "canvas_px": state["canvas_px"],
            "cost": state.get("cost"), "authorized_cost": state.get("authorized_cost"),
            "submission_reported_cost": state.get("submission_reported_cost"),
            "status_reported_cost": state.get("status_reported_cost"),
            "recognition_compatible": state.get("recognition_compatible"),
            "can_resume": bool(state.get("job_id")) and not terminal,
            "manual_reconciliation_required": state["status"] == "pricing_mismatch" or
                (not bool(state.get("job_id")) and state["status"] == "submission_uncertain"),
            "post_attempts": state.get("post_attempts", 0), "last_error": state.get("last_error"),
            "limitations": self.limitations(state)}


def main(argv=None):
    try:
        restarted = enforce_latest(Path(__file__), argv)
        if restarted is not None:
            return restarted
    except UpdateGateError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("health", help="Check the fixed Pro health endpoint without loading a key")
    sub.add_parser("balance", help="Read the current protected customer key's available credits")
    process = sub.add_parser("process", help="Submit once, wait, and verify the returned PNG")
    process.add_argument("--image", required=True, type=Path)
    process.add_argument("--job-dir", required=True, type=Path)
    process.add_argument("--approved-three-credits", action="store_true",
                         help="Explicit approval of the current 3-credit Pro submission")
    process.add_argument("--approved-five-credits", action="store_true",
                         help="Obsolete; cannot authorize a new 3-credit Pro submission")
    process.add_argument("--approved-one-credit", action="store_true",
                         help="Obsolete; cannot authorize a new 3-credit Pro submission")
    process.add_argument("--wait-seconds", type=float, default=900)
    resume = sub.add_parser("resume", help="Resume the same task; never submit another image")
    resume.add_argument("--job-dir", required=True, type=Path)
    resume.add_argument("--wait-seconds", type=float, default=900)
    args = parser.parse_args(argv)
    token = None
    try:
        if hasattr(args, "wait_seconds") and (not math.isfinite(args.wait_seconds) or not 0 <= args.wait_seconds <= 900):
            raise ClientError("--wait-seconds must be between 0 and 900.")
        if args.action != "health":
            token = get_token()
        client = Client(token)
        if args.action == "health":
            result = client.health()
        elif args.action == "balance":
            result = client.balance()
        elif args.action == "process":
            result = client.process(args.image, args.job_dir, approved_three_credits=args.approved_three_credits,
                                    approved_five_credits=args.approved_five_credits,
                                    approved_one_credit=args.approved_one_credit,
                                    wait_seconds=args.wait_seconds)
        else:
            result = client.resume(args.job_dir, wait_seconds=args.wait_seconds)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0 if result.get("ok") else 2
    except (ClientError, OSError) as error:
        message = str(error) if isinstance(error, ClientError) else "Local file operation failed; retain the task directory and resume."
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
        return 1
    finally:
        token = None


if __name__ == "__main__":
    raise SystemExit(main())
