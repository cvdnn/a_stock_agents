"""One-time, move-only migration. Run from the checked-out repository."""
from pathlib import Path
import hashlib
import json
import os
import argparse

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / 'log' / 'skill-suite-migration'


def checked(path):
    path = Path(path)
    resolved = path.resolve()
    if ROOT != resolved and ROOT not in resolved.parents:
        raise RuntimeError(f'Outside repository: {path}')
    return path


def move(source, target):
    source, target = checked(ROOT / source), checked(ROOT / target)
    if not source.exists():
        if target.exists():
            return
        raise FileNotFoundError(source)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Do not fall back to copy+delete when rename is denied.
    os.rename(source, target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['skills', 'core', 'web', 'config', 'shared', 'archive'], required=True)
    args = parser.parse_args()
    LOG.mkdir(parents=True, exist_ok=True)
    protected = ['docs/specs/algorithm/intelligent-selection-funnel-redesign-plan.md',
                 'tests/browser/test_authenticated_workspace.py',
                 'web/css/style.css', 'web/index.html', 'web/js/admin.js',
                 'web/js/app.js', 'web/js/smart_selection.js', 'config/config.yaml']
    proof = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
             for name in protected if (ROOT / name).exists()}
    ledger = LOG / 'initial-hashes.json'
    if not ledger.exists():
        ledger.write_text(json.dumps(proof, indent=2), encoding='utf-8')
    moves = [
        ('.agents/skills', 'skill_bundle/skills'),
        ('scripts/core', 'skill_bundle/runtime/core'),
        ('scripts/server', 'apps/web-console/backend/server'),
        ('web', 'apps/web-console/frontend'),
        ('scripts/tools', 'tools/legacy'),
        ('.agents/prompts', 'skill_bundle/references/prompts'),
        ('config/skills_manifest.json', 'skill_bundle/assets/config/skills_manifest.json'),
        ('config/funnel_strategy.yaml', 'skill_bundle/assets/config/funnel_strategy.yaml'),
        ('config/stock_pools.yaml', 'skill_bundle/assets/config/stock_pools.yaml'),
        ('config/config.yaml', 'local/settings/application.yaml'),
        ('apps/web-console/backend/server/config.py', 'skill_bundle/runtime/core/execution/settings.py'),
        ('apps/web-console/backend/server/db.py', 'skill_bundle/runtime/core/governance/persistence.py'),
        ('apps/web-console/backend/server/agent/tools.py', 'skill_bundle/runtime/core/execution/tools.py'),
        ('apps/web-console/backend/server/llm', 'skill_bundle/runtime/core/llm'),
        ('apps/web-console/backend/server/tasks', 'skill_bundle/runtime/core/jobs'),
        ('apps/web-console/backend/server/services/data_sync_settings.py', 'skill_bundle/runtime/core/data/user_sync_settings.py'),
        ('skill_bundle/skills/astock-strategy-chenxiaoqun/scripts/chenxiaoqun_check.py', 'skill_bundle/runtime/core/strategy/chenxiaoqun.py'),
    ]
    phases = {'skills': moves[:1], 'core': moves[1:2], 'web': moves[2:4],
              'config': moves[4:10], 'shared': moves[10:],
              'archive': [(name, 'log/skill-suite-migration/retired-manifests/' + name.replace('/', '__'))
                          for name in ['config/skills_manifest.yaml', '.agents/manifests/skills_manifest.json',
                                       '.agents/manifests/skills_manifest.yaml']]}
    selected = phases[args.phase]
    for source, target in selected:
        checked(ROOT / source)
        checked(ROOT / target)
        if (ROOT / target).exists():
            raise FileExistsError(target)
        if not (ROOT / source).exists():
            raise FileNotFoundError(source)
    before = {}
    for source, target in selected:
        path = ROOT / source
        files = path.rglob('*') if path.is_dir() else [path]
        before[source] = {str(p.relative_to(path)) if path.is_dir() else '.':
                          hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in files if p.is_file()}
    for source, target in selected:
        move(source, target)
        path = ROOT / target
        files = path.rglob('*') if path.is_dir() else [path]
        after = {str(p.relative_to(path)) if path.is_dir() else '.': hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in files if p.is_file()}
        if after != before[source]:
            raise RuntimeError('Hash verification failed: ' + target)
    (LOG / f'{args.phase}.json').write_text(json.dumps({'moves': selected, 'hashes': before}, indent=2), encoding='utf-8')
    print(json.dumps({'phase': args.phase, 'moved': len(selected), 'hashes_verified': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
