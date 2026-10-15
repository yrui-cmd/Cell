"""Update this installed CNS client from its fixed public GitHub directory.

Only skill code is managed. Credentials, job folders and receiver processes are
never read or changed. Run in a separate process before loading client modules.
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
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPO = 'yrui-cmd/Cell'
BRANCH = 'main'
PREFIX = 'skills/cell-cns-figure/'
LIMIT = 64 * 1024 * 1024
REQUIRED = {'SKILL.md', 'scripts/auto_update.py',
            'backends/fig1/scripts/client.py', 'backends/fig2/scripts/client.py'}


def blob_sha(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def safe_name(name):
    p = PurePosixPath(name)
    if (not name or p.is_absolute() or '\\' in name or ':' in name
            or any(x in ('', '.', '..', '.git') for x in name.split('/'))):
        raise ValueError('Unsafe release path')
    return p


def destination(root, name):
    path = root.joinpath(*safe_name(name).parts)
    # Do not follow junctions/symlinks out of an installed skill.
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Release path escapes installation')
    return path


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'cell-cns-figure-updater',
                                                  'Accept': 'application/vnd.github+json'})
    # Preserve normal proxy configuration, with a direct retry when it is down.
    for opener in (urllib.request.build_opener(),
                   urllib.request.build_opener(urllib.request.ProxyHandler({}))):
        try:
            with opener.open(request, timeout=15) as response:
                data = response.read(LIMIT + 1)
            if len(data) > LIMIT:
                raise ValueError('Release exceeds download limit')
            return data
        except (OSError, urllib.error.URLError):
            continue
    raise OSError('GitHub unavailable; installed version retained')


def remote_release():
    query = urllib.parse.urlencode({'sha': BRANCH, 'path': PREFIX.rstrip('/'), 'per_page': 1})
    commits = json.loads(fetch(f'https://api.github.com/repos/{REPO}/commits?{query}'))
    commit = commits[0]['sha']
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Invalid release commit')
    tree = json.loads(fetch(f'https://api.github.com/repos/{REPO}/git/trees/{commit}?recursive=1'))
    if tree.get('truncated'):
        raise ValueError('Incomplete release tree')
    files = {}
    for row in tree['tree']:
        if row['path'].startswith(PREFIX) and row['type'] != 'tree':
            name = row['path'][len(PREFIX):]
            safe_name(name)
            if row['type'] != 'blob' or row.get('mode') not in ('100644', '100755'):
                raise ValueError('Unsupported release file type')
            files[name] = row['sha']
    if not REQUIRED <= files.keys():
        raise ValueError('Release is missing the CNS updater or client entrypoints')
    return commit, files


def unpack_release(raw, commit, expected):
    files = {}
    prefix = f'Cell-{commit}/{PREFIX}'
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        total = 0
        for info in archive.infolist():
            if not info.filename.startswith(prefix) or info.is_dir():
                continue
            name = info.filename[len(prefix):]
            safe_name(name)
            total += info.file_size
            if total > LIMIT or name in files or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('Invalid release archive')
            data = archive.read(info)
            if name not in expected or blob_sha(data) != expected[name]:
                raise ValueError('Release content hash mismatch')
            files[name] = data
    if files.keys() != expected.keys():
        raise ValueError('Incomplete release archive')
    return files


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.cns-update-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.write(b'0'); stream.flush(); stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def install(root, state_dir, commit, expected, payload, previous):
    changed = [n for n in expected if not destination(root, n).is_file()
               or blob_sha(destination(root, n).read_bytes()) != expected[n]]
    removed = [n for n in previous.get('files', {}) if n not in expected
               and destination(root, n).is_file()]
    backup = state_dir/'backups'/(str(time.time_ns()) + '-' + commit[:12])
    before = {}
    for name in changed + removed:
        target = destination(root, name)
        before[name] = target.read_bytes() if target.is_file() else None
        if before[name] is not None:
            atomic(destination(backup, name), before[name])
    journal = {'commit': commit, 'changed': changed, 'removed': removed,
               'created': [n for n, data in before.items() if data is None]}
    atomic(backup/'update.json', json.dumps(journal).encode())
    try:
        for name in changed:
            atomic(destination(root, name), payload[name])
        for name in removed:
            destination(root, name).unlink()
        # Only advance the installed version once the complete write succeeds.
        atomic(state_dir/'installed.json', json.dumps({'commit': commit, 'files': expected,
               'checked_at': time.time()}, indent=2).encode())
    except BaseException:
        for name, data in before.items():
            target = destination(root, name)
            if data is None:
                target.unlink(missing_ok=True)
            else:
                atomic(target, data)
        raise
    return {'status': 'updated', 'commit': commit, 'backup': str(backup),
            'changed_files': len(changed), 'removed_files': len(removed),
            'reload_skill': True}


def update(root, state_dir, check_only=False):
    root, state_dir = root.resolve(), state_dir.resolve()
    if state_dir.is_relative_to(root):
        raise ValueError('Update state must be outside the skill')
    with lock(state_dir/'update.lock'):
        commit, expected = remote_release()
        old_path = state_dir/'installed.json'
        previous = json.loads(old_path.read_text()) if old_path.exists() else {}
        changed = any(not destination(root,n).is_file()
                      or blob_sha(destination(root,n).read_bytes()) != sha for n,sha in expected.items())
        removed = any(n not in expected and destination(root,n).is_file()
                      for n in previous.get('files',{}))
        if check_only:
            return {'status': 'update_available' if changed or removed else 'up_to_date',
                    'commit': commit, 'applied': False}
        if not changed and not removed:
            atomic(old_path, json.dumps({'commit': commit, 'files': expected,
                   'checked_at': time.time()}).encode())
            return {'status': 'up_to_date', 'commit': commit, 'reload_skill': False}
        payload = unpack_release(fetch(f'https://codeload.github.com/{REPO}/zip/{commit}'), commit, expected)
        return install(root, state_dir, commit, expected, payload, previous)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Report only; do not install')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    local = Path(os.environ.get('LOCALAPPDATA', Path.home()/'.local/share'))
    state_dir = local/'CellCnsFigureUpdater'/hashlib.sha256(str(root).encode()).hexdigest()[:16]
    try:
        result = update(root, state_dir, args.check)
    except Exception as exc:
        result = {'status': 'unavailable', 'error': type(exc).__name__,
                  'message': '更新未完成；保留当前版本和任务进度，不宣称已是最新版。'}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] in ('up_to_date', 'updated', 'update_available') else 1


if __name__ == '__main__':
    raise SystemExit(main())
