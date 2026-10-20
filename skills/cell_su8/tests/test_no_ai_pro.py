"""Offline customer-contract tests: no credentials, real uploads or generation."""
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "no_ai_pro.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("cell_su8_no_ai_pro_test_target", SCRIPT)
api = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = api
SPEC.loader.exec_module(api)
FAKE_KEY = "img_live_offline_test_key.not_a_real_customer_secret"
JOB = "wm_0123456789abcdefabcd"


def png(size=(18, 12), color="#224466"):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


def response(value, code=200, headers=None):
    return api.Response(code, json.dumps(value).encode(), headers or {"Content-Type": "application/json"})


class FakeTransport:
    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if not self.steps:
            raise AssertionError("Unexpected request: %s %s" % (method, path))
        expected_method, expected_path, answer = self.steps.pop(0)
        if (method, path) != (expected_method, expected_path):
            raise AssertionError("Expected %s %s, got %s %s" %
                                 (expected_method, expected_path, method, path))
        if isinstance(answer, Exception):
            raise answer
        return answer


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / "reference.png"
        self.source.write_bytes(png())
        self.source_hash = api.file_digest(self.source)
        self.directory = self.base / "job"
        self.result = png(color="#4488aa")
        self.stderr = io.StringIO()
        self.update_check = patch.object(api, "enforce_latest", return_value=None)
        self.update_check.start()
        self.addCleanup(self.update_check.stop)

    def tearDown(self):
        self.assertEqual(api.file_digest(self.source), self.source_hash, "The original image was modified")
        self.temp.cleanup()

    def client(self, steps):
        transport = FakeTransport(steps)
        return api.Client(FAKE_KEY, transport=transport, sleep=lambda seconds: None,
                          stderr=self.stderr), transport

    def balance(self, credits=10, **extra):
        return response({"ok": True, "available_credits": credits, **extra})

    def status(self, status="completed", result=None, **extra):
        return response({"ok": True, "job_id": JOB, "status": status,
            "source_sha256": self.source_hash, "canvas_px": api.image_info(self.source.read_bytes())["canvas_px"],
            "result_sha256": api.digest(self.result if result is None else result),
            "expires_at": "2099-01-01T00:00:00+00:00", "cost": api.COST, **extra})

    def post(self, **extra):
        return response({"ok": True, "job_id": JOB, "status": "received", "cost": api.COST, **extra}, 201)

    def download(self, data=None, charged="1"):
        data = self.result if data is None else data
        return api.Response(200, data, {"Content-Type": "image/png", "X-Xiaomiao-Charged": charged,
            "X-Content-SHA256": api.digest(data), "X-Xiaomiao-Expires-At": "2099-01-01T00:00:00+00:00"})

    def complete_steps(self):
        return [("GET", "/api/balance", self.balance()),
                ("POST", api.PREFIX, self.post()),
                ("GET", api.PREFIX + "/" + JOB, self.status()),
                ("GET", api.PREFIX + "/" + JOB + "/result", self.download()),
                ("GET", "/api/balance", self.balance(7))]

    def run_process(self, client, **kwargs):
        return client.process(self.source, self.directory, approved_three_credits=True,
                              wait_seconds=0, **kwargs)

    def state(self):
        return json.loads((self.directory / "state.json").read_text(encoding="utf-8"))

    def test_full_contract_original_size_hash_billing_and_customer_routes(self):
        client, transport = self.client(self.complete_steps())
        result = self.run_process(client)
        self.assertTrue(result["ok"])
        self.assertEqual(result["canvas_px"], [18, 12])
        self.assertEqual((self.directory / "result.png").read_bytes(), self.result)
        self.assertTrue(result["recognition_compatible"])
        self.assertEqual(result["post_attempts"], 1)
        self.assertIn("实时可用余额", self.stderr.getvalue())
        self.assertIn("本次费用：3", self.stderr.getvalue())
        receipt = json.loads((self.directory / "result_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["download_charged_header"], "1")
        self.assertEqual(receipt["cost"], 3)
        self.assertEqual(receipt["authorized_cost"], 3)
        self.assertEqual(result["cost"], 3)
        self.assertTrue(self.state()["approved_three_credits"])
        self.assertTrue(receipt["original_unchanged"])
        self.assertFalse(receipt["hidden_watermark_removal_verified"])
        self.assertEqual(receipt["visual_review"], "not_performed_by_client")
        self.assertTrue(all(call[2]["token"] == FAKE_KEY for call in transport.calls))
        self.assertNotIn(FAKE_KEY, (self.directory / "state.json").read_text(encoding="utf-8"))
        self.assertFalse(transport.steps)

    def test_no_approval_never_reads_balance_or_posts(self):
        client, transport = self.client([])
        with self.assertRaises(api.ClientError):
            client.process(self.source, self.directory, wait_seconds=0)
        self.assertFalse(transport.calls)
        self.assertFalse((self.directory / "state.json").exists())

    def test_two_credits_never_submits_and_displays_current_three_credit_cost(self):
        client, transport = self.client([("GET", "/api/balance", self.balance(2))])
        with self.assertRaisesRegex(api.ClientError, "At least 3"):
            self.run_process(client)
        self.assertIn("本次费用：3", self.stderr.getvalue())
        self.assertFalse(any(call[0] == "POST" for call in transport.calls))
        self.assertFalse((self.directory / "state.json").exists())

    def test_obsolete_one_credit_approval_cannot_authorize_new_submission(self):
        client, transport = self.client([])
        with self.assertRaisesRegex(api.ClientError, "now costs 3 credits"):
            client.process(self.source, self.directory, approved_one_credit=True, wait_seconds=0)
        self.assertFalse(transport.calls)
        self.assertFalse((self.directory / "state.json").exists())

    def test_cli_obsolete_one_credit_flag_does_not_authorize_three_credits(self):
        client, transport = self.client([])
        output = io.StringIO()
        with patch.object(api, "get_token", return_value=FAKE_KEY), \
             patch.object(api, "Client", return_value=client), patch.object(api.sys, "stdout", output):
            result = api.main(["process", "--image", str(self.source), "--job-dir", str(self.directory),
                               "--approved-one-credit", "--wait-seconds", "0"])
        self.assertEqual(result, 1)
        self.assertIn("now costs 3 credits", output.getvalue())
        self.assertFalse(transport.calls)

    def test_obsolete_five_credit_approval_cannot_authorize_new_three_credit_submission(self):
        client, transport = self.client([])
        with self.assertRaisesRegex(api.ClientError, "approved-five-credits cannot authorize"):
            client.process(self.source, self.directory, approved_five_credits=True, wait_seconds=0)
        self.assertFalse(transport.calls)
        self.assertFalse((self.directory / "state.json").exists())

    def test_cli_obsolete_five_credit_flag_does_not_authorize_three_credits(self):
        client, transport = self.client([])
        output = io.StringIO()
        with patch.object(api, "get_token", return_value=FAKE_KEY), \
             patch.object(api, "Client", return_value=client), patch.object(api.sys, "stdout", output):
            result = api.main(["process", "--image", str(self.source), "--job-dir", str(self.directory),
                               "--approved-five-credits", "--wait-seconds", "0"])
        self.assertEqual(result, 1)
        self.assertIn("now costs 3 credits", output.getvalue())
        self.assertFalse(transport.calls)

    def test_cli_current_three_credit_flag_accepts_exactly_three_available_credits(self):
        steps = self.complete_steps()
        steps[0] = ("GET", "/api/balance", self.balance(3))
        steps[-1] = ("GET", "/api/balance", self.balance(0))
        client, transport = self.client(steps)
        output = io.StringIO()
        with patch.object(api, "get_token", return_value=FAKE_KEY), \
             patch.object(api, "Client", return_value=client), patch.object(api.sys, "stdout", output):
            code = api.main(["process", "--image", str(self.source), "--job-dir", str(self.directory),
                             "--approved-three-credits", "--wait-seconds", "0"])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result["cost"], 3)
        self.assertEqual(result["authorized_cost"], 3)
        self.assertEqual(sum(call[0] == "POST" for call in transport.calls), 1)

    def legacy_state(self, *, status="processing", cost=1):
        self.directory.mkdir(parents=True, exist_ok=True)
        state = {"schema_version": 1, "service": "no-ai-pro", "origin": api.ORIGIN,
            "api_prefix": api.PREFIX, "source_path": str(self.source.resolve()),
            "source_sha256": self.source_hash, "canvas_px": [18, 12],
            "source_file_canvas_px": [18, 12], "cost": cost,
            "post_attempts": 1, "status": status, "job_id": JOB}
        if cost == 1:
            state["approved_one_credit"] = True
        elif cost == 5:
            state.update(authorized_cost=5, approved_five_credits=True)
        api.atomic_json(self.directory / "state.json", state)
        return state

    def test_legacy_one_credit_resume_keeps_price_and_needs_no_new_three_credit_balance(self):
        self.legacy_state()
        client, transport = self.client([
            ("GET", api.PREFIX + "/" + JOB, self.status(cost=1)),
            ("GET", api.PREFIX + "/" + JOB + "/result", self.download()),
            ("GET", "/api/balance", self.balance(0))])
        result = client.resume(self.directory, wait_seconds=0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["cost"], 1)
        self.assertEqual(self.state()["cost"], 1)
        self.assertTrue(self.state()["approved_one_credit"])
        receipt = json.loads((self.directory / "result_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["cost"], 1)
        self.assertFalse(any(call[0] == "POST" for call in transport.calls))
        self.assertEqual(transport.calls[0][1], api.PREFIX + "/" + JOB)

    def test_completed_legacy_cost_and_existing_receipt_are_not_rewritten(self):
        state = self.legacy_state(status="completed")
        state.update(result_sha256=api.digest(self.result))
        api.atomic_json(self.directory / "state.json", state)
        (self.directory / "result.png").write_bytes(self.result)
        receipt_path = self.directory / "result_receipt.json"
        receipt_path.write_bytes(b'{"cost":1,"legacy_receipt":"frozen"}\n')
        before_state = (self.directory / "state.json").read_bytes()
        before_receipt = receipt_path.read_bytes()
        client, transport = self.client([])
        result = client.process(self.source, self.directory, wait_seconds=0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["cost"], 1)
        self.assertEqual((self.directory / "state.json").read_bytes(), before_state)
        self.assertEqual(receipt_path.read_bytes(), before_receipt)
        self.assertFalse(transport.calls)

    def test_legacy_five_credit_resume_keeps_frozen_price_without_new_balance_precheck(self):
        self.legacy_state(cost=5)
        client, transport = self.client([
            ("GET", api.PREFIX + "/" + JOB, self.status(cost=5)),
            ("GET", api.PREFIX + "/" + JOB + "/result", self.download()),
            ("GET", "/api/balance", self.balance(0))])
        result = client.process(self.source, self.directory, wait_seconds=0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["cost"], 5)
        self.assertEqual(result["authorized_cost"], 5)
        self.assertEqual(self.state()["cost"], 5)
        self.assertTrue(self.state()["approved_five_credits"])
        self.assertNotIn("approved_three_credits", self.state())
        receipt = json.loads((self.directory / "result_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["cost"], 5)
        self.assertEqual(receipt["authorized_cost"], 5)
        self.assertFalse(any(call[0] == "POST" for call in transport.calls))
        self.assertEqual(transport.calls[0][1], api.PREFIX + "/" + JOB)

    def test_completed_five_credit_state_and_original_receipt_stay_byte_identical(self):
        state = self.legacy_state(status="completed", cost=5)
        state.update(result_sha256=api.digest(self.result))
        api.atomic_json(self.directory / "state.json", state)
        (self.directory / "result.png").write_bytes(self.result)
        receipt_path = self.directory / "result_receipt.json"
        receipt_path.write_bytes(b'{"cost":5,"authorized_cost":5,"legacy_receipt":"frozen"}\n')
        before_state = (self.directory / "state.json").read_bytes()
        before_receipt = receipt_path.read_bytes()
        client, transport = self.client([])
        result = client.resume(self.directory, wait_seconds=0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["cost"], 5)
        self.assertEqual(result["authorized_cost"], 5)
        self.assertEqual((self.directory / "state.json").read_bytes(), before_state)
        self.assertEqual(receipt_path.read_bytes(), before_receipt)
        self.assertFalse(transport.calls)

    def test_submission_price_mismatch_preserves_real_job_and_never_reposts(self):
        client, transport = self.client([("GET", "/api/balance", self.balance(3)),
                                        ("POST", api.PREFIX, self.post(cost=1))])
        result = self.run_process(client)
        self.assertEqual(result["status"], "pricing_mismatch")
        self.assertEqual(result["job_id"], JOB)
        self.assertEqual(result["cost"], 1)
        self.assertEqual(result["authorized_cost"], 3)
        self.assertTrue(result["manual_reconciliation_required"])
        self.assertFalse(result["can_resume"])
        self.assertEqual(self.state()["post_attempts"], 1)
        self.assertIn("authorized 3", result["last_error"])
        self.assertEqual(client.resume(self.directory, wait_seconds=0)["status"], "pricing_mismatch")
        self.assertEqual(client.process(self.source, self.directory, wait_seconds=0)["status"], "pricing_mismatch")
        self.assertEqual(len(transport.calls), 2)

    def test_invalid_or_different_ack_cost_is_not_silently_accepted(self):
        for index, cost in enumerate([True, "3", None, 10]):
            with self.subTest(cost=cost):
                client, transport = self.client([("GET", "/api/balance", self.balance()),
                                                ("POST", api.PREFIX, self.post(cost=cost))])
                result = client.process(self.source, self.base / ("cost-%s" % index),
                    approved_three_credits=True, wait_seconds=0)
                self.assertEqual(result["status"], "pricing_mismatch")
                self.assertEqual(result["job_id"], JOB)
                self.assertEqual(len(transport.calls), 2)

    def test_status_price_change_does_not_raise_legacy_price_or_download(self):
        self.legacy_state()
        client, transport = self.client([("GET", api.PREFIX + "/" + JOB, self.status(cost=5))])
        result = client.resume(self.directory, wait_seconds=0)
        self.assertEqual(result["status"], "pricing_mismatch")
        self.assertEqual(result["cost"], 1)
        self.assertEqual(result["status_reported_cost"], 5)
        self.assertTrue(result["manual_reconciliation_required"])
        self.assertEqual(len(transport.calls), 1)

    def test_balance_must_be_live_valid_same_customer_and_sufficient(self):
        invalid = [self.balance(True), self.balance(-1), self.balance("4"), self.balance(None),
                   self.balance(float("nan")), self.balance(0), self.balance(2), self.balance(3, ok=False),
                   response({"ok": True, "available_credits": 3}, 201)]
        for index, answer in enumerate(invalid):
            with self.subTest(index=index):
                client, transport = self.client([("GET", "/api/balance", answer)])
                with self.assertRaises(api.ClientError):
                    client.process(self.source, self.base / ("bad-balance-%s" % index),
                                   approved_three_credits=True, wait_seconds=0)
                self.assertEqual(len(transport.calls), 1)
                self.assertEqual(transport.calls[0][2]["token"], FAKE_KEY)

    def test_resume_does_not_post_or_require_another_available_credit(self):
        steps = [("GET", "/api/balance", self.balance(3)), ("POST", api.PREFIX, self.post()),
                 ("GET", api.PREFIX + "/" + JOB, self.status("processing", expires_at="2000-01-01T00:00:00Z")),
                 ("GET", api.PREFIX + "/" + JOB, self.status()),
                 ("GET", api.PREFIX + "/" + JOB + "/result", self.download()),
                 ("GET", "/api/balance", self.balance(0))]
        client, transport = self.client(steps)
        first = self.run_process(client)
        self.assertFalse(first["ok"])
        self.assertEqual(first["status"], "processing")
        self.assertTrue(self.state()["wait_timed_out"])
        result = client.resume(self.directory, wait_seconds=0)
        self.assertTrue(result["ok"])
        self.assertEqual(sum(c[0] == "POST" for c in transport.calls), 1)
        self.assertEqual(self.state()["expires_at"], "2099-01-01T00:00:00+00:00")

    def test_same_process_directory_automatically_resumes_without_approval(self):
        client, transport = self.client([
            ("GET", "/api/balance", self.balance()), ("POST", api.PREFIX, self.post()),
            ("GET", api.PREFIX + "/" + JOB, self.status("received")),
            ("GET", api.PREFIX + "/" + JOB, self.status()),
            ("GET", api.PREFIX + "/" + JOB + "/result", self.download()),
            ("GET", "/api/balance", self.balance(7))])
        self.run_process(client)
        result = client.process(self.source, self.directory, wait_seconds=0)
        self.assertTrue(result["ok"])
        self.assertEqual(sum(c[0] == "POST" for c in transport.calls), 1)

    def test_post_ack_lost_saves_barrier_and_never_reposts(self):
        client, transport = self.client([("GET", "/api/balance", self.balance()),
            ("POST", api.PREFIX, api.NetworkError("Simulated dropped POST acknowledgement."))])
        result = self.run_process(client)
        self.assertEqual(result["status"], "submission_uncertain")
        self.assertTrue(result["manual_reconciliation_required"])
        self.assertFalse(result["can_resume"])
        self.assertEqual(self.state()["post_attempts"], 1)
        self.assertEqual(client.resume(self.directory, wait_seconds=0)["status"], "submission_uncertain")
        self.assertEqual(self.run_process(client)["status"], "submission_uncertain")
        self.assertEqual(len(transport.calls), 2)

    def test_barrier_is_durable_before_post(self):
        client, transport = self.client(self.complete_steps())
        original_request = transport.request
        def check(method, path, **kwargs):
            if method == "POST":
                state = self.state()
                self.assertEqual(state["status"], "submission_uncertain")
                self.assertIsNone(state["job_id"])
                self.assertEqual(state["source_sha256"], self.source_hash)
            return original_request(method, path, **kwargs)
        transport.request = check
        self.assertTrue(self.run_process(client)["ok"])

    def test_known_job_id_persisted_even_if_post_ack_fields_are_unusual(self):
        steps = self.complete_steps()
        steps[1] = ("POST", api.PREFIX, response({"job_id": JOB, "ok": False}, 500))
        client, transport = self.client(steps)
        original_request = transport.request
        def check(method, path, **kwargs):
            if path == api.PREFIX + "/" + JOB:
                self.assertEqual(self.state()["job_id"], JOB)
            return original_request(method, path, **kwargs)
        transport.request = check
        self.assertTrue(self.run_process(client)["ok"])

    def test_get_can_recover_network_failure_without_resubmission(self):
        steps = self.complete_steps()
        steps.insert(2, ("GET", api.PREFIX + "/" + JOB, api.NetworkError("Simulated transient GET.")))
        client, transport = self.client(steps)
        self.assertTrue(self.run_process(client)["ok"])
        self.assertEqual(sum(c[0] == "POST" for c in transport.calls), 1)

    def test_get_retry_is_bounded_and_retains_real_job(self):
        steps = self.complete_steps()[:2] + [
            ("GET", api.PREFIX + "/" + JOB, api.NetworkError("offline")) for _ in range(3)]
        client, transport = self.client(steps)
        result = self.run_process(client)
        self.assertFalse(result["ok"])
        self.assertEqual(result["job_id"], JOB)
        self.assertTrue(result["can_resume"])
        self.assertEqual(len(transport.calls), 5)

    def test_does_not_follow_server_provided_cross_origin_urls(self):
        steps = self.complete_steps()
        steps[1] = ("POST", api.PREFIX, self.post(status_url="https://evil.invalid/status",
                      result_file_url="https://evil.invalid/result"))
        steps[2] = ("GET", api.PREFIX + "/" + JOB,
                    self.status(result_file_url="https://evil.invalid/result"))
        client, transport = self.client(steps)
        self.assertTrue(self.run_process(client)["ok"])
        self.assertTrue(all(path.startswith("/api/") and "evil" not in path for _, path, _ in transport.calls))

    def test_redirect_response_is_not_accepted_or_reposted(self):
        client, transport = self.client([("GET", "/api/balance", self.balance()),
            ("POST", api.PREFIX, api.Response(307, b"redirect", {"Location": "https://evil.invalid/upload"}))])
        result = self.run_process(client)
        self.assertEqual(result["status"], "submission_uncertain")
        self.assertEqual(len(transport.calls), 2)

    def test_actual_transport_has_no_redirect_handler_and_fixed_route_guard(self):
        transport = api.HttpTransport()
        self.assertTrue(any(isinstance(h, api.NoRedirect) for h in transport.opener.handlers))
        self.assertIsNone(api.NoRedirect().redirect_request(None, None, 302, None, None, "https://evil.invalid"))
        for path in ["https://evil.invalid", "/api/internal/no-ai-pro-jobs", "//evil.invalid", api.PREFIX + "/../../x"]:
            with self.assertRaises(api.ClientError):
                transport.request("GET", path, token=FAKE_KEY)

    def test_actual_transport_sends_only_fixed_https_bearer_and_bounds_body(self):
        class FakeHTTP(io.BytesIO):
            status = 200
            headers = {"Content-Type": "application/json"}
        transport = api.HttpTransport()
        with patch.object(transport.opener, "open", return_value=FakeHTTP(b'{"ok":true}')) as opened:
            answer = transport.request("GET", "/api/balance", token=FAKE_KEY)
            self.assertEqual(answer.status, 200)
            request = opened.call_args.args[0]
            self.assertEqual(request.full_url, "https://xiaomiao-ai.com/api/balance")
            self.assertEqual(request.get_header("Authorization"), "Bearer " + FAKE_KEY)
        with patch.object(transport.opener, "open", return_value=FakeHTTP(b"123456")):
            with self.assertRaises(api.ClientError):
                transport.request("GET", "/api/balance", token=FAKE_KEY, limit=5)

    def test_invalid_worker_credentials_rejected_before_transport(self):
        for token in ["worker_token_not_a_customer", "admin_secret", "img_live_nodot"]:
            with self.assertRaises(api.ClientError):
                api.Client(token, transport=FakeTransport([]))

    def test_bad_result_sha_is_rejected_and_original_charge_header_retained(self):
        wrong = png(color="#ff2200")
        client, transport = self.client(self.complete_steps()[:3] + [
            ("GET", api.PREFIX + "/" + JOB + "/result", self.download(wrong))])
        result = self.run_process(client)
        self.assertFalse(result["ok"])
        self.assertFalse((self.directory / "result.png").exists())
        self.assertIn("SHA-256", result["last_error"])
        self.assertEqual(self.state()["download_charged_header"], "1")
        transport.steps += [("GET", api.PREFIX + "/" + JOB, self.status()),
            ("GET", api.PREFIX + "/" + JOB + "/result", self.download(charged="0")),
            ("GET", "/api/balance", self.balance(7))]
        self.assertTrue(client.resume(self.directory, wait_seconds=0)["ok"])
        self.assertEqual(sum(c[0] == "POST" for c in transport.calls), 1)

    def test_correct_hash_but_wrong_size_is_rejected(self):
        wrong = png(size=(19, 12))
        client, _ = self.client(self.complete_steps()[:2] + [
            ("GET", api.PREFIX + "/" + JOB, self.status(result=wrong)),
            ("GET", api.PREFIX + "/" + JOB + "/result", self.download(wrong))])
        result = self.run_process(client)
        self.assertFalse(result["ok"])
        self.assertIn("dimensions", result["last_error"])
        self.assertFalse((self.directory / "result.png").exists())

    def test_missing_actual_hash_or_wrong_source_identity_never_downloads(self):
        for index, fields in enumerate([{"result_sha256": None}, {"source_sha256": "0" * 64},
                                       {"canvas_px": [9, 9]}, {"job_id": "wm_aaaaaaaaaaaaaaaaaaaa"}]):
            with self.subTest(fields=fields):
                client, transport = self.client(self.complete_steps()[:2] + [
                    ("GET", api.PREFIX + "/" + JOB, self.status(**fields))])
                result = client.process(self.source, self.base / ("mismatch-%s" % index),
                    approved_three_credits=True, wait_seconds=0)
                self.assertFalse(result["ok"])
                self.assertFalse(any(c[1].endswith("/result") for c in transport.calls))

    def test_existing_different_result_never_overwritten(self):
        client, transport = self.client(self.complete_steps()[:2] + [
            ("GET", api.PREFIX + "/" + JOB, self.status("processing")),
            ("GET", api.PREFIX + "/" + JOB, self.status())])
        self.run_process(client)
        target = self.directory / "result.png"
        target.write_bytes(b"different-existing-file")
        result = client.resume(self.directory, wait_seconds=0)
        self.assertFalse(result["ok"])
        self.assertEqual(target.read_bytes(), b"different-existing-file")
        self.assertEqual(len(transport.calls), 4)

    def test_large_result_marks_incompatibility_without_compression_or_regeneration(self):
        self.source.write_bytes(png(size=(1900, 1900)))
        self.source_hash = api.file_digest(self.source)
        image = Image.frombytes("RGB", (1900, 1900), os.urandom(1900 * 1900 * 3))
        output = io.BytesIO()
        image.save(output, format="PNG", compress_level=0)
        self.result = output.getvalue()
        self.assertGreater(len(self.result), api.RECOGNITION_LIMIT)
        client, transport = self.client(self.complete_steps())
        result = self.run_process(client)
        self.assertTrue(result["ok"])
        self.assertFalse(result["recognition_compatible"])
        self.assertEqual((self.directory / "result.png").read_bytes(), self.result)
        self.assertTrue(any("10 MiB" in text for text in result["limitations"]))
        self.assertEqual(sum(c[0] == "POST" for c in transport.calls), 1)

    def test_exif_upright_canvas_is_retained(self):
        output = io.BytesIO()
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (10, 20)).save(output, format="JPEG", exif=exif)
        self.source.write_bytes(output.getvalue())
        self.source_hash = api.file_digest(self.source)
        self.result = png(size=(20, 10))
        client, _ = self.client(self.complete_steps())
        result = self.run_process(client)
        self.assertTrue(result["ok"])
        self.assertEqual(result["canvas_px"], [20, 10])
        self.assertEqual(self.state()["source_file_canvas_px"], [10, 20])

    def test_health_uses_no_credentials(self):
        transport = FakeTransport([("GET", api.PREFIX + "/health", response({"ok": True,
            "service": "no-ai-pro", "engine": "private-implementation", "contract": "private", "cost_per_image": 3}))])
        client = api.Client(transport=transport)
        self.assertEqual(client.health(), {"ok": True, "http_status": 200,
                                          "service": "no-ai-pro", "cost_per_image": 3})
        self.assertIsNone(transport.calls[0][2]["token"])

    def test_cli_failed_update_gate_never_loads_key_constructs_client_or_submits(self):
        output = io.StringIO()
        with patch.object(api, "enforce_latest", side_effect=api.UpdateGateError("Update unavailable")), \
             patch.object(api, "get_token") as key, patch.object(api, "Client") as client, \
             patch.object(api.sys, "stdout", output):
            code = api.main(["process", "--image", str(self.source), "--job-dir", str(self.directory),
                             "--approved-three-credits"])
        self.assertEqual(code, 1)
        self.assertIn("Update unavailable", output.getvalue())
        key.assert_not_called()
        client.assert_not_called()
        self.assertFalse((self.directory / "state.json").exists())

    def test_cli_updated_restart_returns_child_code_without_running_old_client(self):
        with patch.object(api, "enforce_latest", return_value=37), \
             patch.object(api, "get_token") as key, patch.object(api, "Client") as client:
            code = api.main(["balance"])
        self.assertEqual(code, 37)
        key.assert_not_called()
        client.assert_not_called()

    def test_terminal_and_unknown_states_are_retained_without_resubmission(self):
        for index, remote in enumerate(["failed", "cancelled", "expired", "future_status"]):
            with self.subTest(status=remote):
                client, transport = self.client(self.complete_steps()[:2] + [
                    ("GET", api.PREFIX + "/" + JOB, self.status(remote))])
                result = client.process(self.source, self.base / ("terminal-%s" % index),
                    approved_three_credits=True, wait_seconds=0)
                self.assertFalse(result["ok"])
                self.assertEqual(result["status"], "unknown_status" if remote == "future_status" else remote)
                self.assertEqual(sum(c[0] == "POST" for c in transport.calls), 1)

    def test_status_404_stops_same_task(self):
        client, transport = self.client(self.complete_steps()[:2] + [
            ("GET", api.PREFIX + "/" + JOB, response({"ok": False}, 404))])
        result = self.run_process(client)
        self.assertEqual(result["status"], "not_found")
        self.assertFalse(result["can_resume"])
        self.assertEqual(client.resume(self.directory, wait_seconds=0)["status"], "not_found")
        self.assertEqual(len(transport.calls), 3)

    def test_after_download_balance_failure_does_not_undo_verified_result(self):
        client, _ = self.client(self.complete_steps()[:-1] + [
            ("GET", "/api/balance", response({"ok": False}, 401))])
        result = self.run_process(client)
        self.assertTrue(result["ok"])
        self.assertIsNone(self.state()["balance_after"])

    def test_completed_resume_verifies_local_result_and_repairs_missing_receipt(self):
        client, transport = self.client(self.complete_steps())
        self.assertTrue(self.run_process(client)["ok"])
        receipt = self.directory / "result_receipt.json"
        receipt.unlink()
        self.assertTrue(client.resume(self.directory, wait_seconds=0)["ok"])
        self.assertTrue(receipt.is_file())
        self.assertEqual(len(transport.calls), 5)

    def test_atomic_published_result_recovers_without_querying_expired_server(self):
        client, transport = self.client(self.complete_steps()[:2] + [
            ("GET", api.PREFIX + "/" + JOB, self.status("processing"))])
        self.run_process(client)
        state = self.state()
        state.update(status="downloading", expected_result_sha256=api.digest(self.result),
                     download_charged_header="1")
        api.atomic_json(self.directory / "state.json", state)
        (self.directory / "result.png").write_bytes(self.result)
        transport.steps = [("GET", "/api/balance", self.balance(7))]
        self.assertTrue(client.resume(self.directory, wait_seconds=0)["ok"])
        self.assertEqual(len(transport.calls), 4)

    def test_os_lock_blocks_concurrent_use_and_releases(self):
        with api.job_lock(self.directory):
            with self.assertRaises(api.ClientError):
                with api.job_lock(self.directory):
                    self.fail("Concurrent lock acquired")
        with api.job_lock(self.directory):
            pass

    def test_wait_invalid_budget_fails_before_any_request(self):
        client, transport = self.client([])
        for value in [-1, 901, float("nan"), True]:
            with self.subTest(value=value), self.assertRaises(api.ClientError):
                client.process(self.source, self.directory, approved_three_credits=True, wait_seconds=value)
        self.assertFalse(transport.calls)

    def test_poll_time_budget_is_not_an_unbounded_loop(self):
        clock = [0.0]
        steps = self.complete_steps()[:2] + [
            ("GET", api.PREFIX + "/" + JOB, self.status("processing")) for _ in range(2)]
        client, transport = self.client(steps)
        client.monotonic = lambda: clock[0]
        client.sleep = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
        result = client.process(self.source, self.directory, approved_three_credits=True, wait_seconds=5)
        self.assertFalse(result["ok"])
        self.assertEqual(clock[0], 5)
        self.assertEqual(len(transport.calls), 3)
        self.assertTrue(result["can_resume"])

    def test_same_wait_deadline_applies_to_download_and_optional_final_balance(self):
        clock = [100.0]
        client, transport = self.client(self.complete_steps())
        client.monotonic = lambda: clock[0]
        client.sleep = lambda seconds: clock.__setitem__(0, clock[0] + seconds)
        result = client.process(self.source, self.directory, approved_three_credits=True, wait_seconds=20)
        self.assertTrue(result["ok"])
        # Preflight and POST are outside the bounded polling phase; status,
        # result and optional final balance use the same absolute deadline.
        self.assertTrue(all(call[2]["deadline"] == 120.0 for call in transport.calls[2:]))


if __name__ == "__main__":
    unittest.main()
