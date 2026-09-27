#!/usr/bin/env python3
"""Create/verify a deterministic content manifest; does not lock or copy files."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def content_digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def make_manifest(directory: Path, excluded: Path | None = None) -> dict:
    root=directory.resolve()
    if not root.is_dir():raise ValueError('Snapshot directory does not exist.')
    entries=[]
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise ValueError('Symlinks are not allowed in evidence snapshots.')
        if path.is_file() and (excluded is None or path.resolve()!=excluded.resolve()):
            before=path.stat()
            digest=content_digest(path)
            after=path.stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                raise ValueError('File changed while hashing: '+str(path))
            entries.append({'path':path.relative_to(root).as_posix(),'size':after.st_size,'sha256':digest})
    canonical=json.dumps(entries,sort_keys=True,separators=(',',':')).encode('utf-8')
    return {'version':'1.0','snapshot_sha256':hashlib.sha256(canonical).hexdigest(),'files':entries,
            'note':'Content manifest only. Keep a versioned copy; this program does not make files immutable.'}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',required=True,type=Path)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--output',type=Path);group.add_argument('--verify',type=Path)
    p.add_argument('--quiet',action='store_true')
    p.add_argument('--verbose', dest='quiet', action='store_false', help='Print local diagnostic output.')
    p.set_defaults(quiet=True)
    a=p.parse_args()
    try:
        target=a.output or a.verify
        manifest=make_manifest(a.directory,target)
        if a.verify:
            previous=json.loads(a.verify.read_text(encoding='utf-8'))
            if previous['snapshot_sha256']!=manifest['snapshot_sha256']:
                raise ValueError('Evidence snapshot content changed.')
            if not a.quiet:print('VERIFIED '+manifest['snapshot_sha256'])
        else:
            if a.output.exists():raise ValueError('Refusing to overwrite an existing snapshot manifest.')
            a.output.parent.mkdir(parents=True,exist_ok=True)
            a.output.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            if not a.quiet:print(manifest['snapshot_sha256'])
    except (OSError,ValueError,KeyError) as error:p.exit(2,f'ERROR: {error}\n')
    return 0
if __name__=='__main__':raise SystemExit(main())
