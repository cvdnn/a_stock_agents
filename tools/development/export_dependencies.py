"""Export the committed lockfile; does not build/install or update dependency locks."""
from pathlib import Path
import shutil
import subprocess
import re


def base_dependencies_match(project, lock):
    def normalize(value):
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)(.*)', value)
        return (re.sub(r'[-_.]+', '-', match[1]).lower(), match[2].replace(' ', ''))
    declared = {normalize(value) for value in project['project']['dependencies']}
    package = next(value for value in lock['package'] if value['name'] == 'a-stock-agents')
    recorded = {(value['name'], value.get('specifier', ''))
                for value in package['metadata']['requires-dist'] if not value.get('marker')}
    return declared == recorded

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'skill_bundle/bundle.json').is_file())

if __name__ == '__main__':
    try:
        import tomllib
    except ImportError:
        raise SystemExit('Dependency export requires Python 3.11+ for TOML inspection; runtime supports Python 3.9+')
    project = tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))
    lock = tomllib.loads((ROOT/'uv.lock').read_text(encoding='utf-8'))
    if not base_dependencies_match(project, lock):
        raise SystemExit('Base dependency declarations differ from uv.lock. Refresh the lock explicitly before export.')
    uv = shutil.which('uv')
    if not uv: raise SystemExit('uv required to export the authoritative uv.lock')
    subprocess.run([uv, 'export', '--frozen', '--offline', '--no-dev', '--no-emit-project',
                    '--no-hashes', '--output-file', 'requirements.txt'], cwd=ROOT, check=True)
