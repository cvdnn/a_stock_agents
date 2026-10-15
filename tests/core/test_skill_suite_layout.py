"""Migration regressions: unique authorities and reference lifecycle."""
from pathlib import Path
import importlib.util
import json
import pytest

from core.workspace import PACKAGE_ROOT, RUNTIME_ROOT, SKILLS_ROOT, MANIFEST_PATH, bundle_resource, default_data_root

ROOT=Path(__file__).resolve().parents[2]


def reference_manager():
    spec=importlib.util.spec_from_file_location('tested_astock_references',ROOT/'tools/host_adapters/references.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_has_one_runtime_and_complete_skill_catalog():
    ids={item['id'] for item in json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))['skills']}
    found={path.parent.name for path in SKILLS_ROOT.glob('*/SKILL.md')}
    assert len(ids)==19
    assert found==ids|{'a-stock-agents'}
    assert RUNTIME_ROOT==PACKAGE_ROOT/'runtime'
    assert not (SKILLS_ROOT/'a-stock-agents/scripts/core').exists()
    assert not (ROOT/'scripts/core').exists()
    assert not (ROOT/'config/skills_manifest.json').exists()


def test_bundle_resources_cannot_escape():
    with pytest.raises(ValueError):bundle_resource('../local/settings/application.yaml')


def test_reference_registration_is_idempotent_and_uninstall_preserves_source(tmp_path):
    manager=reference_manager()
    target=tmp_path/'source'
    doc=target/'sample/SKILL.md'
    doc.parent.mkdir(parents=True)
    doc.write_text('---\nname: sample\ndescription: sample\n---\n',encoding='utf-8')
    entry=tmp_path/'host/skills'
    first=manager.register_reference(target,entry)
    assert first['status']=='success',first
    assert entry.resolve()==target.resolve()
    second=manager.register_reference(target,entry)
    assert second['status']=='success' and second['changed'] is False
    result=manager.unregister_reference(entry)
    assert result['status']=='success'
    assert doc.is_file()
    assert not manager.is_reference(entry)


def test_reference_never_overwrites_a_physical_skill_directory(tmp_path):
    manager=reference_manager()
    target=tmp_path/'source'
    (target/'sample').mkdir(parents=True)
    (target/'sample/SKILL.md').write_text('sample',encoding='utf-8')
    entry=tmp_path/'host/skills'
    entry.mkdir(parents=True)
    keep=entry/'keep.txt'
    keep.write_text('owned by another source',encoding='utf-8')
    result=manager.register_reference(target,entry)
    assert result['status']=='conflict'
    assert keep.read_text(encoding='utf-8')=='owned by another source'


def test_uninstall_refuses_unowned_reference(tmp_path):
    manager=reference_manager()
    entry=tmp_path/'not-owned'
    entry.mkdir()
    result=manager.unregister_reference(entry)
    assert result['reason_code']=='REFERENCE_NOT_OWNED'
    assert entry.is_dir()


def test_release_user_data_is_separate_from_installed_code_on_all_platforms(tmp_path, monkeypatch):
    package = tmp_path / 'host-cache/version/skill_bundle'
    package.mkdir(parents=True)
    (package / 'bundle.json').write_text('{"distribution":"release"}', encoding='utf-8')
    home = tmp_path / 'user'
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: home))
    assert default_data_root(package, {}, 'win32') == home / 'AppData/Local/a_stock_agents'
    assert default_data_root(package, {}, 'darwin') == home / 'Library/Application Support/a_stock_agents'
    assert default_data_root(package, {}, 'linux') == home / '.local/share/a_stock_agents'
    assert default_data_root(package, {'XDG_DATA_HOME': 'relative'}, 'linux') == home / '.local/share/a_stock_agents'
    assert default_data_root(package, {'XDG_DATA_HOME': str(tmp_path/'xdg')}, 'linux') == tmp_path/'xdg/a_stock_agents'


def test_explicit_data_binding_and_development_default_are_preserved(tmp_path):
    package = tmp_path / 'skill_bundle'
    package.mkdir()
    (package / 'bundle.json').write_text('{}', encoding='utf-8')
    assert default_data_root(package, {}, 'linux') == tmp_path
    assert default_data_root(package, {'A_STOCK_WORKSPACE_ROOT': str(tmp_path/'private')}, 'linux') == tmp_path/'private'


def test_release_archive_is_generated_without_private_data_or_source_mutation(tmp_path, monkeypatch):
    # 2026-10-15（P0-02）：移除 A_STOCK_NO_BUILD=1 可跳过口子——打包归档行为属 P0 门禁，
    # 不允许环境变量一键静默跳过（skip 不计入 failed，会掩盖发布链路回归）。
    import zipfile
    from tools.packaging import common
    monkeypatch.setattr(common, 'get_log_path', lambda *args: tmp_path/'build.log')
    marker_before = (PACKAGE_ROOT/'bundle.json').read_bytes()
    destination = common.package_project(tmp_path/'candidate.zip', platform='codex')
    with zipfile.ZipFile(destination) as archive:
        names = archive.namelist()
        assert len([name for name in names if name.endswith('/SKILL.md')]) == 20
        assert not any(set(Path(name).parts) & {'local','output','log','temp','.agents','.venv','__pycache__','apps','tests'} for name in names)
        marker = json.loads(archive.read('skill_bundle/bundle.json'))
        assert marker['distribution'] == 'release'
        instructions = json.loads(archive.read('INSTALL.json'))
        assert instructions['native_import_verified'] is False
        assert instructions['mode'] == 'release-candidate-collection'
        assert archive.read('skill_bundle/runtime/core/workspace.py') == (RUNTIME_ROOT/'core/workspace.py').read_bytes()
    assert (PACKAGE_ROOT/'bundle.json').read_bytes() == marker_before
