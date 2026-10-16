"""Reference-only skill discovery. Never copy a skill or traverse its target on uninstall."""
from __future__ import annotations
import argparse
import json
import os
import stat
import subprocess
from pathlib import Path


def is_reference(path: Path) -> bool:
    try:
        value = path.lstat()
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(getattr(value, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))


def register_reference(target, entry):
    target, entry = Path(target).resolve(), Path(entry).absolute()
    has_skill = (target / 'SKILL.md').is_file() or any(target.glob('*/SKILL.md'))
    if not target.is_dir() or not has_skill:
        return {'status': 'error', 'reason_code': 'INVALID_SKILLS_ROOT'}
    if entry == target or target in entry.parents or entry in target.parents:
        return {'status': 'error', 'reason_code': 'REFERENCE_CYCLE'}
    if os.path.lexists(entry):
        if is_reference(entry) and entry.resolve() == target:
            return {'status': 'success', 'message': 'Already bound to the unique source', 'changed': False,
                    'entry': str(entry), 'target': str(target)}
        return {'status': 'conflict', 'reason_code': 'ENTRY_ALREADY_EXISTS', 'entry': str(entry)}
    entry.parent.mkdir(parents=True, exist_ok=True)
    try:
        link_target = os.path.relpath(target, entry.parent) if os.name != 'nt' else str(target)
        entry.symlink_to(link_target, target_is_directory=True)
        kind = 'symlink'
    except OSError as exc:
        if os.name != 'nt' or str(target).startswith('\\\\'):
            return {'status': 'error', 'reason_code': 'REFERENCE_UNAVAILABLE', 'detail': str(exc), 'copy_fallback': False}
        adapter = Path(__file__).with_name('windows_junction.ps1')
        result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-File', str(adapter),
                                 '-Target', str(target), '-Entry', str(entry)], capture_output=True, text=True)
        if result.returncode or not is_reference(entry) or entry.resolve() != target:
            return {'status': 'error', 'reason_code': 'REFERENCE_UNAVAILABLE', 'detail': result.stderr,
                    'copy_fallback': False}
        kind = 'junction'
    # Store only a binding receipt, no business configuration or skill content.
    receipt = entry.parent / ('.' + entry.name + '.astock-reference.json')
    receipt.write_text(json.dumps({'entry': str(entry), 'target': str(target), 'type': kind}, indent=2), encoding='utf-8')
    return {'status': 'success', 'message': 'Reference created; host scan remains to be verified',
            'entry': str(entry), 'target': str(target), 'type': kind, 'changed': True}


def unregister_reference(entry):
    entry = Path(entry).absolute()
    receipt = entry.parent / ('.' + entry.name + '.astock-reference.json')
    if not receipt.is_file():
        return {'status': 'conflict', 'reason_code': 'REFERENCE_NOT_OWNED'}
    data = json.loads(receipt.read_text(encoding='utf-8'))
    if data.get('entry') != str(entry) or not is_reference(entry):
        return {'status': 'conflict', 'reason_code': 'REFERENCE_CHANGED'}
    if entry.exists() and entry.resolve() != Path(data['target']).resolve():
        return {'status': 'conflict', 'reason_code': 'REFERENCE_CHANGED'}
    if data['type'] == 'junction':
        os.rmdir(entry)  # remove only the reparse entry, never its target
    else:
        entry.unlink()
    receipt.unlink()
    return {'status': 'success', 'target_preserved': True}


def register_skills(skills_root, host_skills_dir):
    """P0-10 逐技能粒度平级注册：在宿主技能根创建 20 个平级独立链接。"""
    skills_root, host_skills_dir = Path(skills_root).resolve(), Path(host_skills_dir).absolute()
    if not skills_root.is_dir():
        return {'status': 'error', 'reason_code': 'INVALID_SKILLS_ROOT'}
    skill_paths = sorted([p.parent for p in skills_root.glob('*/SKILL.md') if p.parent.is_dir()])
    if not skill_paths:
        return {'status': 'error', 'reason_code': 'NO_SKILLS_FOUND'}
    host_skills_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    any_changed = False
    for sp in skill_paths:
        skill_id = sp.name
        skill_entry = host_skills_dir / skill_id
        res = register_reference(sp, skill_entry)
        results[skill_id] = res
        if res.get('changed', False):
            any_changed = True
    suite_receipt = host_skills_dir / '.a-stock-suite.json'
    suite_receipt.write_text(json.dumps({
        'skills_root': str(skills_root),
        'host_skills_dir': str(host_skills_dir),
        'skill_count': len(skill_paths),
        'skills': [sp.name for sp in skill_paths],
    }, indent=2), encoding='utf-8')
    all_ok = all(r.get('status') in ('success', 'conflict') for r in results.values())
    return {
        'status': 'success' if all_ok else 'error',
        'mode': 'per-skill',
        'source': str(skills_root),
        'host_skills_dir': str(host_skills_dir),
        'registered_count': len([r for r in results.values() if r.get('status') == 'success']),
        'skill_count': len(skill_paths),
        'changed': any_changed,
        'details': results,
    }


def unregister_skills(host_skills_dir):
    """卸载 host_skills_dir 下全部由 a-stock-agents 注册的技能链接。"""
    host_skills_dir = Path(host_skills_dir).absolute()
    if not host_skills_dir.is_dir():
        return {'status': 'error', 'reason_code': 'DIR_NOT_FOUND'}
    removed = []
    for receipt_file in sorted(host_skills_dir.glob('.*.astock-reference.json')):
        entry_name = receipt_file.name[1:-len('.astock-reference.json')]
        entry_path = host_skills_dir / entry_name
        res = unregister_reference(entry_path)
        if res.get('status') == 'success':
            removed.append(entry_name)
    suite_receipt = host_skills_dir / '.a-stock-suite.json'
    if suite_receipt.is_file():
        suite_receipt.unlink()
    return {'status': 'success', 'removed': removed, 'count': len(removed)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['register', 'unregister', 'inspect', 'register-skills', 'unregister-skills'])
    parser.add_argument('--target', type=Path)
    parser.add_argument('--entry', required=True, type=Path)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.action == 'register':
        if args.target is None: parser.error('--target required')
        result = register_reference(args.target, args.entry)
    elif args.action == 'unregister':
        result = unregister_reference(args.entry)
    elif args.action == 'register-skills':
        if args.target is None: parser.error('--target required')
        result = register_skills(args.target, args.entry)
    elif args.action == 'unregister-skills':
        result = unregister_skills(args.entry)
    else:
        result = {'entry': str(args.entry.absolute()), 'is_reference': is_reference(args.entry),
                  'exists': args.entry.exists(), 'target': str(args.entry.resolve())}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('status', 'success') == 'success' else 1


if __name__ == '__main__':
    raise SystemExit(main())
