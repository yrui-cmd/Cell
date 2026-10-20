"""Fail-closed updater for this skill's fixed public GitHub directory.

Only released code is managed. Coordination, manifests, backups and rollback
records live outside the skill. No credential or task directory is inspected.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

REPO = "yrui-cmd/Cell"
BRANCH = "main"
PREFIX = "skills/cell_su8/"
LIMIT = 64 * 1024 * 1024
MANIFEST_LIMIT = 4 * 1024 * 1024
MAX_FILES = 4096
REQUIRED = {"SKILL.md", "scripts/auto_update.py", "scripts/update_gate.py",
            "scripts/no_ai_pro.py", "scripts/run_cell_su8.py", "scripts/run_cell_su8.ps1"}
CODE_DIRS = {"scripts", "references", "agents", "tests"}
SUFFIXES = {".py", ".ps1", ".sh", ".jsx", ".js", ".mjs", ".cjs", ".md",
            ".txt", ".json", ".yaml", ".yml", ".toml"}
FORBIDDEN_DIRS = {".git", ".svn", "__pycache__", ".venv", "node_modules", "jobs",
                  "outputs", "output", "secrets", "credentials", "config"}
SECRET_NAMES = {"settings.json", "runtime-profile.json", "credentials.json", "secrets.json",
                "tokens.json", "api_key", "api-key", "api_key.txt", "api-key.txt",
                "worker_token", "worker-token", "worker_key", "worker-key"}
SHA = re.compile(r"[0-9a-f]{40}\Z")
DEVICES = re.compile(r"(?:con|prn|aux|nul|conin\$|conout\$|com[1-9¹²³]|lpt[1-9¹²³])\Z", re.I)


class UpdateError(RuntimeError):
    def __init__(self, code, *, backup=None, rollback_failed=False):
        super().__init__(code)
        self.code, self.backup, self.rollback_failed = code, backup, rollback_failed


def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _identity(name):
    return unicodedata.normalize("NFC", name).casefold()


def safe_name(name, *, directory=False):
    if not isinstance(name, str) or not name or len(name) > 500:
        raise UpdateError("unsafe_release_path")
    if any(ord(c) < 32 or ord(c) == 127 or c in '\\:<>"|?*' for c in name):
        raise UpdateError("unsafe_release_path")
    parts = name.split("/")
    for part in parts:
        lower = part.casefold()
        if (not part or part in {".", ".."} or part.endswith((".", " "))
                or lower in FORBIDDEN_DIRS or lower in SECRET_NAMES
                or lower == ".env" or lower.startswith(".env.")
                or DEVICES.fullmatch(part.split(".", 1)[0])):
            raise UpdateError("unsafe_release_path")
    if not ((not directory and name == "SKILL.md") or
            (parts[0] in CODE_DIRS and (directory or len(parts) >= 2))):
        raise UpdateError("unmanaged_release_path")
    if not directory and name != "SKILL.md" and PurePosixPath(name).suffix.lower() not in SUFFIXES:
        raise UpdateError("unsupported_release_file")
    return PurePosixPath(name)


def _validate_files(files, *, required=True):
    if not isinstance(files, dict) or not 0 < len(files) <= MAX_FILES:
        raise UpdateError("invalid_release_manifest")
    identities = set()
    for name, digest in files.items():
        safe_name(name)
        if not isinstance(digest, str) or not SHA.fullmatch(digest):
            raise UpdateError("invalid_blob_hash")
        identity = _identity(name)
        if identity in identities:
            raise UpdateError("windows_release_collision")
        identities.add(identity)
    for name in identities:
        parts = name.split("/")
        if any("/".join(parts[:i]) in identities for i in range(1, len(parts))):
            raise UpdateError("release_file_directory_collision")
    if required and not REQUIRED.issubset(files):
        raise UpdateError("missing_required_release_files")
    return dict(sorted(files.items()))


def _no_links(path):
    path = Path(path)
    for component in reversed((path, *path.parents)):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode) or
                getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise UpdateError("linked_installation_path")


def destination(root, name):
    path = Path(root).joinpath(*safe_name(name).parts)
    _no_links(path)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return path
    if not stat.S_ISREG(mode):
        raise UpdateError("installation_target_not_regular")
    return path


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port
            or parsed.fragment or not (
                (parsed.hostname == "api.github.com" and parsed.path.startswith(f"/repos/{REPO}/"))
                or (parsed.hostname == "codeload.github.com" and parsed.path.startswith(f"/{REPO}/zip/")))):
        raise UpdateError("unsupported_release_origin")
    request = urllib.request.Request(url, headers={"User-Agent": "cell-su8-updater",
                                                  "Accept": "application/vnd.github+json"})
    proxies = (urllib.request.ProxyHandler(), urllib.request.ProxyHandler({}),
               urllib.request.ProxyHandler({}))
    for attempt, proxy in enumerate(proxies):
        try:
            opener = urllib.request.build_opener(proxy, _NoRedirect())
            with opener.open(request, timeout=15) as response:
                data = response.read(LIMIT + 1)
            if len(data) > LIMIT:
                raise UpdateError("release_download_too_large")
            return data
        except (OSError, urllib.error.URLError):
            if attempt == 0:
                time.sleep(0.2)
            continue
    raise UpdateError("release_network_unavailable")


def latest_commit():
    query = urllib.parse.urlencode({"sha": BRANCH, "path": PREFIX.rstrip("/"), "per_page": 1})
    value = json.loads(fetch(f"https://api.github.com/repos/{REPO}/commits?{query}"))
    if not isinstance(value, list) or not value or not isinstance(value[0], dict):
        raise UpdateError("invalid_release_commit")
    commit = value[0].get("sha")
    if not isinstance(commit, str) or not SHA.fullmatch(commit):
        raise UpdateError("invalid_release_commit")
    return commit


def release_tree(commit):
    tree = json.loads(fetch(f"https://api.github.com/repos/{REPO}/git/trees/{commit}?recursive=1"))
    if not isinstance(tree, dict) or tree.get("truncated") or not isinstance(tree.get("tree"), list):
        raise UpdateError("incomplete_release_tree")
    files = {}
    for row in tree["tree"]:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise UpdateError("invalid_release_tree")
        if not row["path"].startswith(PREFIX):
            continue
        name = row["path"][len(PREFIX):]
        if row.get("type") == "tree":
            safe_name(name, directory=True)
            if row.get("mode") not in {"040000", "40000"}:
                raise UpdateError("unsupported_release_file_type")
            continue
        safe_name(name)
        if row.get("type") != "blob" or row.get("mode") not in {"100644", "100755"}:
            raise UpdateError("unsupported_release_file_type")
        if name in files:
            raise UpdateError("duplicate_release_path")
        files[name] = row.get("sha")
    return _validate_files(files)


def unpack_release(raw, commit, expected):
    expected = _validate_files(expected)
    if not isinstance(raw, bytes) or len(raw) > LIMIT:
        raise UpdateError("invalid_release_archive")
    files, identities, total = {}, set(), 0
    base = f"Cell-{commit}/{PREFIX.rstrip('/')}"
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for info in archive.infolist():
            if info.filename == base + "/":
                continue
            if not info.filename.startswith((base + "/", base + "\\")):
                continue
            name = info.filename[len(base) + 1:]
            directory = info.is_dir()
            if directory:
                name = name[:-1]
            safe_name(name, directory=directory)
            identity = _identity(name)
            if identity in identities:
                raise UpdateError("windows_archive_collision")
            identities.add(identity)
            mode = info.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if (stat.S_ISLNK(mode) or info.external_attr & 0x400 or info.flag_bits & 1
                    or kind not in ({0, stat.S_IFDIR} if directory else {0, stat.S_IFREG})):
                raise UpdateError("unsupported_archive_file_type")
            if directory:
                continue
            total += info.file_size
            if total > LIMIT or info.file_size < 0 or info.compress_size > LIMIT:
                raise UpdateError("expanded_release_too_large")
            if name not in expected or name in files:
                raise UpdateError("unexpected_archive_file")
            data = archive.read(info)
            if blob_sha(data) != expected[name]:
                raise UpdateError("release_blob_hash_mismatch")
            files[name] = data
    if files.keys() != expected.keys():
        raise UpdateError("incomplete_release_archive")
    return files


def _root_hash(root):
    return hashlib.sha256(os.path.normcase(str(root)).encode("utf-8")).hexdigest()


def state_directory(root):
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
    return local / "CellSu8Updater" / _root_hash(Path(root).absolute())[:16]


def _manifest_digest(value):
    identity = {k: value[k] for k in ("schema_version", "repo", "branch", "prefix", "root_hash", "commit", "files")}
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _state(root, commit, files):
    value = {"schema_version": 1, "repo": REPO, "branch": BRANCH, "prefix": PREFIX,
             "root_hash": _root_hash(root), "commit": commit, "files": files,
             "checked_at": time.time()}
    value["manifest_sha256"] = _manifest_digest(value)
    return value


def load_previous(root, state_dir):
    path = state_dir / "installed.json"
    _no_links(path)
    if not path.exists():
        return {}
    if not path.is_file() or path.stat().st_size > MANIFEST_LIMIT:
        raise UpdateError("invalid_installed_state")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(value, dict) or value.get("schema_version") != 1
                or value.get("repo") != REPO or value.get("branch") != BRANCH
                or value.get("prefix") != PREFIX or value.get("root_hash") != _root_hash(root)
                or not isinstance(value.get("commit"), str) or not SHA.fullmatch(value["commit"])
                or value.get("manifest_sha256") != _manifest_digest(value)):
            raise ValueError()
        value["files"] = _validate_files(value["files"], required=False)
        if not {"SKILL.md", "scripts/auto_update.py"}.issubset(value["files"]):
            raise ValueError()
        return value
    except (KeyError, TypeError, ValueError, UpdateError):
        raise UpdateError("invalid_installed_state") from None


def atomic(path, data):
    path = Path(path)
    _no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _no_links(path)
    descriptor, name = tempfile.mkstemp(prefix=".su8-update-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


@contextmanager
def lock(path):
    path = Path(path)
    _no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise UpdateError("update_locked") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def _changes(root, expected, previous):
    changed, removed, preserved = [], [], []
    for name, digest in expected.items():
        target = destination(root, name)
        if not target.is_file() or blob_sha(target.read_bytes()) != digest:
            changed.append(name)
    for name, digest in previous.get("files", {}).items():
        if name in expected:
            continue
        target = destination(root, name)
        if target.is_file():
            if blob_sha(target.read_bytes()) == digest:
                removed.append(name)
            else:
                preserved.append(name)
    return changed, removed, preserved


def install(root, state_dir, commit, expected, payload, previous):
    changed, removed, preserved = _changes(root, expected, previous)
    if any(name not in payload or blob_sha(payload[name]) != expected[name] for name in changed):
        raise UpdateError("unverified_install_payload")
    backup = state_dir / "backups" / (str(time.time_ns()) + "-" + commit[:12] + "-" + uuid.uuid4().hex[:8])
    before = {}
    for name in changed + removed:
        target = destination(root, name)
        before[name] = target.read_bytes() if target.is_file() else None
        if before[name] is not None:
            atomic(destination(backup, name), before[name])
    installed = state_dir / "installed.json"
    old_state = installed.read_bytes() if installed.is_file() else None
    journal = {"status": "prepared", "commit": commit, "changed": changed, "removed": removed,
               "created": [n for n, data in before.items() if data is None],
               "preserved_modified_files": preserved}
    atomic(backup / "update.json", _json_bytes(journal))
    if old_state is not None:
        atomic(backup / "installed.before.json", old_state)
    try:
        for name in changed:
            atomic(destination(root, name), payload[name])
        for name in removed:
            destination(root, name).unlink()
        if any(not destination(root, n).is_file() or blob_sha(destination(root, n).read_bytes()) != sha
               for n, sha in expected.items()):
            raise UpdateError("installed_blob_hash_mismatch")
        atomic(installed, _json_bytes(_state(root, commit, expected)))
    except BaseException:
        failures = []
        for name, data in reversed(list(before.items())):
            try:
                target = destination(root, name)
                if data is None:
                    target.unlink(missing_ok=True)
                else:
                    atomic(target, data)
            except BaseException:
                failures.append(name)
        try:
            _no_links(installed)
            if old_state is None:
                installed.unlink(missing_ok=True)
            elif not installed.is_file() or installed.read_bytes() != old_state:
                atomic(installed, old_state)
        except BaseException:
            failures.append("installed.json")
        journal.update(status="rollback_failed" if failures else "rolled_back", rollback_failures=failures)
        try:
            atomic(backup / "update.json", _json_bytes(journal))
        except BaseException:
            failures.append("rollback_record")
        raise UpdateError("rollback_failed" if failures else "installation_failed_rolled_back",
                          backup=str(backup), rollback_failed=bool(failures)) from None
    journal["status"] = "committed"
    try:
        atomic(backup / "update.json", _json_bytes(journal))
    except OSError:
        # installed.json and all code have already committed and been verified.
        pass
    return {"status": "updated", "commit": commit, "backup": str(backup),
            "changed_files": len(changed), "removed_files": len(removed),
            "preserved_modified_files": len(preserved), "reload_skill": True}


def _update(root, state_dir, check_only):
    root, state_dir = Path(root).absolute(), Path(state_dir).absolute()
    _no_links(root)
    _no_links(state_dir)
    if not root.is_dir() or root.is_relative_to(state_dir) or state_dir.is_relative_to(root):
        raise UpdateError("invalid_update_locations")
    with lock(state_dir / "update.lock"):
        # Always query this directory's latest remote commit, even with a cache.
        commit = latest_commit()
        previous = load_previous(root, state_dir)
        expected = (_validate_files(previous["files"]) if previous.get("commit") == commit
                    else release_tree(commit))
        changed, removed, preserved = _changes(root, expected, previous)
        if check_only:
            return {"status": "update_available" if changed or removed else "up_to_date",
                    "commit": commit, "applied": False, "reload_skill": False}
        if not changed and not removed:
            atomic(state_dir / "installed.json", _json_bytes(_state(root, commit, expected)))
            return {"status": "up_to_date", "commit": commit, "reload_skill": False,
                    "preserved_modified_files": len(preserved)}
        payload = (unpack_release(fetch(f"https://codeload.github.com/{REPO}/zip/{commit}"), commit, expected)
                   if changed else {})
        return install(root, state_dir, commit, expected, payload, previous)


def update(root, state_dir, check_only=False):
    try:
        return _update(root, state_dir, bool(check_only))
    except Exception as exc:
        result = {"status": "unavailable", "error": exc.code if isinstance(exc, UpdateError)
                  else "release_validation_or_io_failed", "rollback_failed": bool(getattr(exc, "rollback_failed", False)),
                  "message": "更新未完成；保留任务，不宣称已是最新版。"}
        if getattr(exc, "backup", None):
            result["backup"] = exc.backup
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check only; do not install or advance installed.json")
    args = parser.parse_args(argv)
    root = Path(__file__).absolute().parents[1]
    result = update(root, state_directory(root), args.check)
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["status"] in {"up_to_date", "updated", "update_available"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
