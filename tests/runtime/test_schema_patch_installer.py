"""Targeted Windows installer must preserve local code and roll back failed checks."""
from pathlib import Path
import subprocess
from unittest.mock import patch
import pytest
from scripts import fix_groq_schema as installer

ROOT=Path(__file__).resolve().parents[2]


def setup_local(tmp_path, monkeypatch):
    target=tmp_path/'wireless_assistant/a_transport.py'
    tests=tmp_path/'tests/runtime/test_a_transport.py'
    target.parent.mkdir(parents=True);tests.parent.mkdir(parents=True)
    target.write_text((ROOT/'wireless_assistant/a_transport.py').read_text().replace(installer.INSERT,'')+'\n# user local change\n')
    tests.write_text((ROOT/'tests/runtime/test_a_transport.py').read_text().replace(installer.TEST_ADDITION,''))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(installer.sys,'argv',['fix_groq_schema.py','--offline-only'])
    return target,tests


def test_targeted_patch_preserves_edits_and_is_idempotent(tmp_path,monkeypatch):
    target,tests=setup_local(tmp_path,monkeypatch)
    with patch.object(installer.socket,'socket') as sock,patch.object(installer.subprocess,'run'):
        sock.return_value.__enter__.return_value.connect_ex.return_value=1
        installer.main()
        first=(target.read_bytes(),tests.read_bytes())
        installer.main()
    assert (target.read_bytes(),tests.read_bytes())==first
    assert target.read_text().endswith('# user local change\n')
    assert target.read_text().count(installer.INSERT)==1
    assert len(list(tmp_path.glob('schema-fix-backup-*')))==1


def test_targeted_patch_rolls_back_failed_checks(tmp_path,monkeypatch):
    target,tests=setup_local(tmp_path,monkeypatch)
    before=(target.read_bytes(),tests.read_bytes())
    with patch.object(installer.socket,'socket') as sock,patch.object(installer.subprocess,'run',side_effect=[None, subprocess.CalledProcessError(1,['pytest'])]):
        sock.return_value.__enter__.return_value.connect_ex.return_value=1
        with pytest.raises(RuntimeError,match='restored'):installer.main()
    assert (target.read_bytes(),tests.read_bytes())==before


def test_targeted_patch_refuses_changed_anchor(tmp_path,monkeypatch):
    target,tests=setup_local(tmp_path,monkeypatch)
    target.write_text(target.read_text().replace(installer.ANCHOR,'    definitions = original.pop("$defs")\n'))
    before=(target.read_bytes(),tests.read_bytes())
    with patch.object(installer.socket,'socket') as sock,patch.object(installer.subprocess,'run') as run:
        sock.return_value.__enter__.return_value.connect_ex.return_value=1
        with pytest.raises(RuntimeError,match='No files overwritten'):installer.main()
        run.assert_not_called()
    assert (target.read_bytes(),tests.read_bytes())==before
