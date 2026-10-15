"""Failure and source-protection contracts for engineering entry points."""
from pathlib import Path
import subprocess
import pytest

from tools.development import manage
from tools.legacy import update


@pytest.mark.parametrize('with_uv', [False, True])
def test_dependency_failure_stops_before_diagnosis_or_success(tmp_path, monkeypatch, capsys, with_uv):
    monkeypatch.setattr(manage, 'ROOT', tmp_path)
    monkeypatch.setattr(manage.shutil, 'which', lambda name: 'uv' if with_uv else None)
    calls = []
    def execute(command, **kwargs):
        calls.append(command)
        if 'install' in command:
            raise subprocess.CalledProcessError(7, command)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(manage.subprocess, 'run', execute)
    with pytest.raises(subprocess.CalledProcessError):
        manage.setup([])
    assert not any(any(str(value).endswith('doctor.py') for value in command) for command in calls)
    assert 'environment ready' not in capsys.readouterr().out


def test_retired_update_refuses_overwrite_without_touching_source(tmp_path):
    source = tmp_path/'source.py'
    source.write_text('user change', encoding='utf-8')
    result = update.apply_update_from_zip(tmp_path/'candidate.zip', tmp_path/'backup')
    assert result is False
    assert source.read_text(encoding='utf-8') == 'user change'
    assert not (tmp_path/'backup').exists()
    with pytest.raises(SystemExit) as stopped:
        update.main()
    assert stopped.value.code == 2
