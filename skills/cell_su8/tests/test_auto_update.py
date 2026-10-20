"""Offline updater tests. All files are disposable; no network or key is read."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
import urllib.error
import zipfile

SOURCE = Path(__file__).resolve().parents[1] / "scripts/auto_update.py"
SPEC = importlib.util.spec_from_file_location("su8_auto_update_under_test", SOURCE)
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)
A, B = "a" * 40, "b" * 40
REAL_FETCH = api.fetch


def contents(label="new"):
    return {name: (label + ":" + name + "\n").encode() for name in sorted(api.REQUIRED)}


def archive(commit, files, *, extras=(), omit=(), override=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            if name not in omit:
                z.writestr(f"Cell-{commit}/{api.PREFIX}{name}", (override or {}).get(name, data))
        for name, data, mode in extras:
            info = zipfile.ZipInfo(f"Cell-{commit}/{api.PREFIX}{name}")
            info.create_system = 3
            info.external_attr = mode << 16
            z.writestr(info, data)
    return buffer.getvalue()


class Remote:
    def __init__(self, files=None, commit=A):
        self.files = contents() if files is None else files
        self.commit = commit
        self.calls = []
        self.tree_overrides = None
        self.zip_override = None

    def fetch(self, url):
        self.calls.append(url)
        if "/commits?" in url:
            return json.dumps([{"sha": self.commit}]).encode()
        if "/git/trees/" in url:
            rows = [{"path": api.PREFIX + name, "type": "blob", "mode": "100644",
                     "sha": api.blob_sha(data)} for name, data in self.files.items()]
            return json.dumps(self.tree_overrides if self.tree_overrides is not None else
                              {"truncated": False, "tree": rows}).encode()
        if "codeload.github.com/" in url:
            return self.zip_override if self.zip_override is not None else archive(self.commit, self.files)
        raise AssertionError("Unexpected URL")


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="su8-updater-offline-")
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root, self.state = base / "skill", base / "external-state"
        self.root.mkdir()
        self.remote = Remote()
        self.fetch = patch.object(api, "fetch", side_effect=self.remote.fetch)
        self.fetch.start()
        self.addCleanup(self.fetch.stop)

    def put(self, files):
        for name, data in files.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file() and not p.is_symlink()}

    def update(self, check=False):
        return api.update(self.root, self.state, check)

    def seed_installed(self, files=None, commit=A):
        files = self.remote.files if files is None else files
        self.put(files)
        self.state.mkdir(exist_ok=True)
        value = api._state(self.root.absolute(), commit, {n: api.blob_sha(d) for n, d in files.items()})
        (self.state / "installed.json").write_bytes(api._json_bytes(value))

    def assert_unavailable_unchanged(self, before):
        result = self.update()
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(self.snapshot(), before)
        return result

    def test_up_to_date_queries_remote_even_when_cached_and_hashes_every_file(self):
        self.seed_installed()
        result = self.update()
        self.assertEqual(result["status"], "up_to_date")
        self.assertEqual(len(self.remote.calls), 1)
        self.assertIn("/commits?", self.remote.calls[0])
        self.assertIn("sha=main", self.remote.calls[0])
        self.assertIn("path=skills%2Fcell_su8", self.remote.calls[0])
        # Equal commit does not excuse a modified file: verify the full release.
        (self.root / "scripts/no_ai_pro.py").write_bytes(b"damaged")
        result = self.update()
        self.assertEqual(result["status"], "updated")
        self.assertEqual((self.root / "scripts/no_ai_pro.py").read_bytes(), self.remote.files["scripts/no_ai_pro.py"])
        self.assertEqual(sum("/git/trees/" in u for u in self.remote.calls), 0)

    def test_uncached_up_to_date_validates_tree_and_local_blobs_without_archive(self):
        self.put(self.remote.files)
        self.assertEqual(self.update()["status"], "up_to_date")
        self.assertEqual(len(self.remote.calls), 2)
        self.assertTrue((self.state / "installed.json").is_file())
        self.assertFalse((self.state / "backups").exists())

    def test_old_version_updates_and_saves_external_verified_manifest_and_backups(self):
        old = contents("old")
        self.seed_installed(old, B)
        result = self.update()
        self.assertEqual(result["status"], "updated")
        backup = Path(result["backup"])
        self.assertTrue(backup.is_relative_to(self.state))
        self.assertFalse(backup.is_relative_to(self.root))
        for name, data in self.remote.files.items():
            self.assertEqual((self.root / name).read_bytes(), data)
            self.assertEqual((backup / name).read_bytes(), old[name])
        self.assertEqual(json.loads((backup / "update.json").read_text())["status"], "committed")
        installed = api.load_previous(self.root, self.state)
        self.assertEqual(installed["commit"], A)
        self.assertEqual(installed["files"], {n: api.blob_sha(d) for n, d in self.remote.files.items()})

    def test_check_never_installs_or_advances_manifest(self):
        self.seed_installed(contents("old"), B)
        before = self.snapshot()
        manifest = (self.state / "installed.json").read_bytes()
        result = self.update(check=True)
        self.assertEqual(result["status"], "update_available")
        self.assertFalse(result["applied"])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(manifest, (self.state / "installed.json").read_bytes())
        self.assertFalse((self.state / "backups").exists())
        self.assertFalse(any("codeload" in u for u in self.remote.calls))

    def test_network_failure_is_closed_and_does_not_print_remote_error_content(self):
        self.seed_installed(contents("old"), B)
        before = self.snapshot()
        with patch.object(api, "fetch", side_effect=OSError("private body must never appear")):
            result = self.assert_unavailable_unchanged(before)
        self.assertNotIn("private body", json.dumps(result))
        self.assertEqual(api.load_previous(self.root, self.state)["commit"], B)

    def test_fetch_third_get_succeeds_after_default_and_first_direct_tls_failures(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, limit):
                self.limit = limit
                return b"verified fake response"
        response = Response()
        handlers = [object(), object(), object()]
        openers = [Mock(), Mock(), Mock()]
        openers[0].open.side_effect = urllib.error.URLError("simulated TLS failure")
        openers[1].open.side_effect = OSError("simulated connection failure")
        openers[2].open.return_value = response
        with patch.object(api.urllib.request, "ProxyHandler", side_effect=handlers) as proxy, \
             patch.object(api.urllib.request, "build_opener", side_effect=openers) as build, \
             patch.object(api.time, "sleep") as sleep:
            actual = REAL_FETCH(f"https://api.github.com/repos/{api.REPO}/commits?sha=main")
        self.assertEqual(actual, b"verified fake response")
        self.assertEqual(proxy.call_args_list, [call(), call({}), call({})])
        self.assertEqual(build.call_count, 3)
        for index, opener in enumerate(openers):
            self.assertIs(build.call_args_list[index].args[0], handlers[index])
            self.assertIsInstance(build.call_args_list[index].args[1], api._NoRedirect)
            self.assertEqual(opener.open.call_count, 1)
            self.assertEqual(opener.open.call_args.kwargs, {"timeout": 15})
            self.assertTrue(opener.open.call_args.args[0].full_url.startswith("https://api.github.com/"))
        sleep.assert_called_once_with(0.2)
        self.assertEqual(response.limit, api.LIMIT + 1)

    def test_three_failed_gets_fail_closed_and_preserve_installed_version(self):
        self.seed_installed(contents("old"), B)
        before = self.snapshot()
        manifest = (self.state / "installed.json").read_bytes()
        openers = [Mock(), Mock(), Mock()]
        for opener in openers:
            opener.open.side_effect = urllib.error.URLError("private TLS body must not be printed")
        with patch.object(api, "fetch", side_effect=REAL_FETCH), \
             patch.object(api.urllib.request, "build_opener", side_effect=openers) as build, \
             patch.object(api.time, "sleep") as sleep:
            result = self.assert_unavailable_unchanged(before)
        self.assertEqual(build.call_count, 3)
        self.assertTrue(all(opener.open.call_count == 1 for opener in openers))
        self.assertEqual(result["error"], "release_network_unavailable")
        self.assertNotIn("private TLS body", json.dumps(result))
        self.assertEqual(manifest, (self.state / "installed.json").read_bytes())
        sleep.assert_called_once_with(0.2)

    def test_corrupt_state_cannot_delete_jobs_or_any_other_user_file(self):
        self.put(contents("old"))
        self.put({"jobs/customer/result.png": b"customer original", "scripts/user_helper.py": b"personal"})
        self.state.mkdir()
        (self.state / "installed.json").write_text('{"files":{"../victim":"a"}}')
        result = self.assert_unavailable_unchanged(self.snapshot())
        self.assertEqual(result["error"], "invalid_installed_state")
        self.assertEqual(len(self.remote.calls), 1)  # Latest remote check still occurred.

    def test_well_formed_but_tampered_manifest_fails_integrity_before_deletion(self):
        self.seed_installed(contents("old"), B)
        self.put({"scripts/personal.py": b"keep"})
        path = self.state / "installed.json"
        value = json.loads(path.read_text())
        value["files"]["scripts/personal.py"] = api.blob_sha(b"keep")
        path.write_text(json.dumps(value))
        self.assert_unavailable_unchanged(self.snapshot())

    def test_managed_deletion_preserves_jobs_extra_files_and_user_modified_old_code(self):
        old = contents("old") | {"scripts/obsolete.py": b"managed old", "scripts/modified.py": b"managed version"}
        self.seed_installed(old, B)
        self.put({"jobs/customer/input.png": b"source", "outputs/final.png": b"result",
                  "scripts/user_helper.py": b"user helper", "scripts/modified.py": b"edited by user"})
        result = self.update()
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["removed_files"], 1)
        self.assertEqual(result["preserved_modified_files"], 1)
        self.assertFalse((self.root / "scripts/obsolete.py").exists())
        for name, data in {"jobs/customer/input.png": b"source", "outputs/final.png": b"result",
                           "scripts/user_helper.py": b"user helper", "scripts/modified.py": b"edited by user"}.items():
            self.assertEqual((self.root / name).read_bytes(), data)

    def test_missing_required_tree_file_fails_closed(self):
        del self.remote.files["scripts/update_gate.py"]
        self.assert_unavailable_unchanged(self.snapshot())

    def test_truncated_tree_fails_closed(self):
        self.remote.tree_overrides = {"truncated": True, "tree": []}
        self.assert_unavailable_unchanged(self.snapshot())

    def test_archive_hash_mismatch_and_missing_file_fail_before_any_install(self):
        self.put(contents("old"))
        before = self.snapshot()
        for raw in (archive(A, self.remote.files, override={"SKILL.md": b"mismatch"}),
                    archive(A, self.remote.files, omit={"SKILL.md"})):
            self.remote.zip_override = raw
            self.assert_unavailable_unchanged(before)
        self.assertFalse((self.state / "installed.json").exists())
        self.assertFalse((self.state / "backups").exists())

    def test_tree_symlink_and_submodule_are_rejected(self):
        for mode, kind in (("120000", "blob"), ("160000", "commit")):
            rows = [{"path": api.PREFIX + n, "type": "blob", "mode": "100644", "sha": api.blob_sha(d)}
                    for n, d in self.remote.files.items()]
            rows.append({"path": api.PREFIX + "scripts/link.py", "type": kind, "mode": mode, "sha": A})
            self.remote.tree_overrides = {"truncated": False, "tree": rows}
            self.assert_unavailable_unchanged(self.snapshot())

    def test_archive_path_traversal_secrets_windows_devices_and_symlink_are_rejected(self):
        self.put(contents("old"))
        before = self.snapshot()
        for name, mode in (("../outside.py", stat.S_IFREG | 0o644),
                           ("scripts/../../jobs/task.py", stat.S_IFREG | 0o644),
                           ("scripts/evil\\path.py", stat.S_IFREG | 0o644),
                           ("scripts/NUL.txt", stat.S_IFREG | 0o644),
                           ("scripts/COM1.py", stat.S_IFREG | 0o644),
                           ("scripts/evil.py:payload", stat.S_IFREG | 0o644),
                           ("scripts/worker-key.dpapi", stat.S_IFREG | 0o644),
                           ("scripts/.env", stat.S_IFREG | 0o644),
                           ("jobs/customer.txt", stat.S_IFREG | 0o644),
                           ("scripts/link.py", stat.S_IFLNK | 0o777)):
            with self.subTest(name=name):
                self.remote.zip_override = archive(A, self.remote.files, extras=[(name, b"bad", mode)])
                self.assert_unavailable_unchanged(before)

    def test_windows_case_and_file_directory_tree_collisions_are_rejected(self):
        for extra in ("scripts/NO_AI_PRO.py", "scripts/no_ai_pro.py/child.py"):
            files = self.remote.files | {extra: b"collision"}
            remote = Remote(files)
            with patch.object(api, "fetch", side_effect=remote.fetch):
                self.assert_unavailable_unchanged(self.snapshot())

    def test_windows_case_collision_in_archive_is_rejected(self):
        self.remote.zip_override = archive(A, self.remote.files,
            extras=[("scripts/NO_AI_PRO.py", b"bad", stat.S_IFREG | 0o644)])
        self.assert_unavailable_unchanged(self.snapshot())

    def test_existing_symlink_or_reparse_path_is_never_followed(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        victim = outside / "no_ai_pro.py"
        victim.write_bytes(b"outside must stay")
        try:
            (self.root / "scripts").symlink_to(outside, target_is_directory=True)
        except OSError:
            # A Windows account lacking symlink privilege still exercises the
            # same FILE_ATTRIBUTE_REPARSE_POINT rejection deterministically.
            original = Path.lstat
            class Reparse:
                st_mode = stat.S_IFDIR | 0o755
                st_file_attributes = 0x400
            def fake(path, *args, **kwargs):
                return Reparse() if path == self.root / "scripts" else original(path, *args, **kwargs)
            with patch.object(Path, "lstat", fake):
                self.assertEqual(self.update()["status"], "unavailable")
        else:
            self.assertEqual(self.update()["status"], "unavailable")
        self.assertEqual(victim.read_bytes(), b"outside must stay")

    def test_state_inside_skill_is_rejected_without_touching_task_files(self):
        self.put({"jobs/customer.txt": b"keep"})
        result = api.update(self.root, self.root / "jobs/update-state")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual((self.root / "jobs/customer.txt").read_bytes(), b"keep")

    def test_process_lock_rejects_a_second_updater_without_fetching(self):
        self.state.mkdir()
        code = ("import importlib.util,sys; s=importlib.util.spec_from_file_location('u',sys.argv[1]);"
                "u=importlib.util.module_from_spec(s);s.loader.exec_module(u);"
                "c=u.lock(u.Path(sys.argv[2]));c.__enter__();print('LOCKED',flush=True);"
                "sys.stdin.readline();c.__exit__(None,None,None)")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
        child = subprocess.Popen([sys.executable, "-B", "-c", code, str(SOURCE), str(self.state / "update.lock")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        try:
            self.assertEqual(child.stdout.readline().strip(), "LOCKED")
            result = self.update()
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["error"], "update_locked")
            self.assertEqual(self.remote.calls, [])
        finally:
            child.communicate("stop\n", timeout=10)
        self.assertEqual(child.returncode, 0)

    def test_mid_write_failure_rolls_back_changed_removed_and_created_files(self):
        old = contents("old") | {"scripts/obsolete.py": b"old helper"}
        del old["scripts/update_gate.py"]
        self.seed_installed(old, B)
        self.put({"jobs/task/original.png": b"customer original"})
        before = self.snapshot()
        manifest = (self.state / "installed.json").read_bytes()
        original = api.atomic
        writes = []
        def fail_one(path, data):
            path = Path(path)
            if path.is_relative_to(self.root) and data.startswith(b"new:"):
                writes.append(path)
                if len(writes) == 3:
                    raise OSError("simulated disk write error")
            return original(path, data)
        with patch.object(api, "atomic", side_effect=fail_one):
            result = self.assert_unavailable_unchanged(before)
        self.assertEqual(result["error"], "installation_failed_rolled_back")
        self.assertFalse(result["rollback_failed"])
        self.assertEqual((self.state / "installed.json").read_bytes(), manifest)
        journal = json.loads((Path(result["backup"]) / "update.json").read_text())
        self.assertEqual(journal["status"], "rolled_back")
        self.assertIn("scripts/update_gate.py", journal["created"])
        self.assertFalse((self.root / "scripts/update_gate.py").exists())

    def test_manifest_write_failure_restores_code_and_keeps_previous_commit(self):
        self.seed_installed(contents("old"), B)
        before = self.snapshot()
        original = api.atomic
        def fail_manifest(path, data):
            if Path(path) == self.state / "installed.json":
                raise OSError("state write failed")
            return original(path, data)
        with patch.object(api, "atomic", side_effect=fail_manifest):
            result = self.assert_unavailable_unchanged(before)
        self.assertEqual(result["error"], "installation_failed_rolled_back")
        self.assertEqual(api.load_previous(self.root, self.state)["commit"], B)

    def test_rollback_failure_is_explicit_and_recorded_outside_skill(self):
        self.seed_installed(contents("old"), B)
        original = api.atomic
        first = self.root / "SKILL.md"
        second = self.root / "scripts/auto_update.py"
        def fail(path, data):
            path = Path(path)
            if path == second and data.startswith(b"new:"):
                raise OSError("install failed")
            if path == first and data.startswith(b"old:"):
                raise OSError("rollback failed")
            return original(path, data)
        with patch.object(api, "atomic", side_effect=fail):
            result = self.update()
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["error"], "rollback_failed")
        self.assertTrue(result["rollback_failed"])
        journal = json.loads((Path(result["backup"]) / "update.json").read_text())
        self.assertEqual(journal["status"], "rollback_failed")
        self.assertIn("SKILL.md", journal["rollback_failures"])
        self.assertEqual(api.load_previous(self.root, self.state)["commit"], B)


if __name__ == "__main__":
    unittest.main()
