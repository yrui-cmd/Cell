import importlib.util
import io
import json
from pathlib import Path
import zipfile

import pytest

PATH = Path(__file__).resolve().parents[1]/'skills/cell-cns-figure/scripts/auto_update.py'
spec = importlib.util.spec_from_file_location('cns_auto_update', PATH)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def release():
    data = {name: ('new ' + name).encode() for name in updater.REQUIRED}
    return data, {name: updater.blob_sha(value) for name,value in data.items()}


def archive(data, commit='a'*40):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as z:
        for name,value in data.items():
            z.writestr(f'Cell-{commit}/{updater.PREFIX}{name}',value)
    return output.getvalue()


def test_update_backups_and_idempotency(tmp_path, monkeypatch):
    root, state = tmp_path/'skill', tmp_path/'state'
    root.mkdir()
    (root/'SKILL.md').write_bytes(b'old skill')
    (root/'job.json').write_bytes(b'keep customer state')
    data, hashes = release()
    monkeypatch.setattr(updater,'remote_release',lambda: ('a'*40,hashes))
    monkeypatch.setattr(updater,'fetch',lambda url: archive(data))
    report = updater.update(root,state)
    assert report['status']=='updated'
    assert (Path(report['backup'])/'SKILL.md').read_bytes()==b'old skill'
    assert (root/'job.json').read_bytes()==b'keep customer state'
    assert all((root/n).read_bytes()==v for n,v in data.items())
    assert updater.update(root,state)['status']=='up_to_date'
    assert json.loads((state/'installed.json').read_text())['commit']=='a'*40


def test_check_and_network_failure_do_not_modify_skill(tmp_path,monkeypatch):
    root,state=tmp_path/'skill',tmp_path/'state'
    root.mkdir(); (root/'SKILL.md').write_bytes(b'old')
    data,hashes=release()
    monkeypatch.setattr(updater,'remote_release',lambda: ('a'*40,hashes))
    assert updater.update(root,state,True)['status']=='update_available'
    assert (root/'SKILL.md').read_bytes()==b'old'
    def failure(): raise OSError('offline')
    monkeypatch.setattr(updater,'remote_release',failure)
    with pytest.raises(OSError): updater.update(root,state)
    assert (root/'SKILL.md').read_bytes()==b'old'
    assert not (state/'installed.json').exists()


def test_archive_hash_and_path_validation():
    data,hashes=release()
    assert updater.unpack_release(archive(data),'a'*40,hashes)==data
    data['SKILL.md']=b'tampered'
    with pytest.raises(ValueError): updater.unpack_release(archive(data),'a'*40,hashes)
    for name in ('../outside','C:/secret','x\\y','/absolute','x/../../bad'):
        with pytest.raises(ValueError): updater.safe_name(name)


def test_write_failure_rolls_back(tmp_path,monkeypatch):
    root,state=tmp_path/'skill',tmp_path/'state'
    root.mkdir(); (root/'SKILL.md').write_bytes(b'old')
    data={'SKILL.md':b'new','script.py':b'new script'}
    hashes={n:updater.blob_sha(v) for n,v in data.items()}
    original=updater.atomic
    def fail_one(path, value):
        if path==root/'script.py': raise PermissionError('busy')
        return original(path,value)
    monkeypatch.setattr(updater,'atomic',fail_one)
    with pytest.raises(PermissionError): updater.install(root,state,'a'*40,hashes,data,{})
    assert (root/'SKILL.md').read_bytes()==b'old'
    assert not (root/'script.py').exists()
    assert not (state/'installed.json').exists()


def test_removes_only_previously_managed_files(tmp_path):
    root,state=tmp_path/'skill',tmp_path/'state'
    root.mkdir(); (root/'old.py').write_bytes(b'obsolete'); (root/'local.json').write_bytes(b'local')
    report=updater.install(root,state,'a'*40,{'SKILL.md':updater.blob_sha(b'new')},
                           {'SKILL.md':b'new'},{'files':{'old.py':'oldhash'}})
    assert not (root/'old.py').exists()
    assert (root/'local.json').read_bytes()==b'local'
    assert (Path(report['backup'])/'old.py').read_bytes()==b'obsolete'
