#!/usr/bin/env python3
"""Local progress and artifact records. No model, network or experiment execution."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def configure_utf8_stdio() -> None:
    """Keep redirected CLI output Unicode-safe on legacy Windows locales."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Refusing a symlink state file.')
    fd, temporary = tempfile.mkstemp(prefix='.session-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def init(directory: Path, model_id: str, mode: str, topic: str) -> Path:
    if not model_id.strip() or not topic.strip():
        raise ValueError('Model ID and research topic are required.')
    if mode not in ('live','offline','replay','synthetic'):
        raise ValueError('Invalid run mode.')
    if directory.exists():
        raise ValueError('Run directory already exists; use a new one or resume its state.')
    directory.mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    state = {'version':'2.0','created_at':now,'model_id':model_id,'mode':mode,'topic':topic,
             'last_step':0,'progress_history':[], 'artifact_records':[]}
    path = directory/'session.json'
    atomic_json(path, state)
    for folder in ('evidence','records','results'):
        (directory/folder).mkdir()
    return path


def load_state(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError('Refusing a symlink state file.')
    state = json.loads(path.read_text(encoding='utf-8'))
    if state.get('version') != '2.0' or type(state.get('last_step')) is not int:
        raise ValueError('Invalid session state.')
    return state


def advance(path: Path, step: int, model_id: str) -> str:
    if type(step) is not int or not 1 <= step <= 6:
        raise ValueError('Progress step must be an integer from 1 to 6.')
    state = load_state(path)
    if state['model_id'] != model_id:
        raise ValueError('A run cannot change its host model.')
    if step <= state['last_step']:
        return ''  # Backtracking/repeated calls are deliberately silent.
    if step != state['last_step'] + 1:
        raise ValueError('Cannot skip a public progress step.')
    line = f'第{step}步'
    state['last_step'] = step
    state['progress_history'].append({'step':step,'message':line,'at':datetime.now(timezone.utc).isoformat()})
    atomic_json(path,state)
    return line


def record(path: Path, stage: str, artifact: Path, model_id: str) -> None:
    state = load_state(path)
    if state['model_id'] != model_id:
        raise ValueError('A run cannot change its host model.')
    if stage not in {f'S{i:02d}' for i in range(14)}:
        raise ValueError('Internal stage must be S00 through S13.')
    if artifact.is_symlink() or not artifact.is_file():
        raise ValueError('Artifact must be an existing regular non-symlink file.')
    root = path.resolve().parent
    try:
        relative = artifact.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError('Recorded artifacts must be inside this run directory.') from exc
    raw = artifact.read_bytes()
    state['artifact_records'].append({'stage':stage,'path':relative,
        'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw),
        'recorded_at':datetime.now(timezone.utc).isoformat(),
        'meaning':'Artifact content recorded; semantic completion is not certified.'})
    atomic_json(path,state)


def main() -> int:
    configure_utf8_stdio()
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('init');p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--model-id',required=True);p.add_argument('--mode',default='live',choices=['live','offline','replay','synthetic']);p.add_argument('--topic',required=True)
    p=sub.add_parser('progress');p.add_argument('--state',type=Path,required=True);p.add_argument('--step',type=int,required=True);p.add_argument('--model-id',required=True)
    p=sub.add_parser('record');p.add_argument('--state',type=Path,required=True);p.add_argument('--stage',required=True);p.add_argument('--artifact',type=Path,required=True);p.add_argument('--model-id',required=True)
    args=parser.parse_args()
    try:
        if args.command=='init':
            init(args.run_dir,args.model_id,args.mode,args.topic)
        elif args.command=='record':
            record(args.state,args.stage,args.artifact,args.model_id)
        else:
            message=advance(args.state,args.step,args.model_id)
            if message:print(message)
        return 0
    except (OSError,ValueError,KeyError,TypeError) as error:
        print('ERROR: '+str(error),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
