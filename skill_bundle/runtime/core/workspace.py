"""Unique code roots and separately bound writable workspace."""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict, Tuple

PACKAGE_ROOT = next((path for path in Path(__file__).resolve().parents
                     if (path / 'bundle.json').is_file()), None)
if PACKAGE_ROOT is None or json.loads((PACKAGE_ROOT / 'bundle.json').read_text(encoding='utf-8')).get('name') != 'a_stock_agents':
    raise RuntimeError('Valid a_stock_agents bundle marker required')
RUNTIME_ROOT = PACKAGE_ROOT / 'runtime'
if (PACKAGE_ROOT / 'skills').is_dir():
    SKILLS_ROOT = PACKAGE_ROOT / 'skills'
elif PACKAGE_ROOT.name == 'a-stock-agents' and (PACKAGE_ROOT.parent / 'a-stock-agents').is_dir():
    SKILLS_ROOT = PACKAGE_ROOT.parent
else:
    SKILLS_ROOT = PACKAGE_ROOT / 'skills'
ASSETS_ROOT = PACKAGE_ROOT / 'assets'
REFERENCES_ROOT = PACKAGE_ROOT / 'references'
MANIFEST_PATH = ASSETS_ROOT / 'config' / 'skills_manifest.json'
def default_data_root(package_root, environment=None, platform=None):
    """Development data stay local; installed versions never write host caches."""
    environment = os.environ if environment is None else environment
    platform = __import__('sys').platform if platform is None else platform
    explicit = environment.get('A_STOCK_WORKSPACE_ROOT') or environment.get('A_STOCK_AGENTS_ROOT')
    if explicit:
        return Path(explicit).expanduser().resolve()
    marker = json.loads((package_root / 'bundle.json').read_text(encoding='utf-8'))
    if marker.get('distribution') != 'release':
        return package_root.parent
    home = Path.home()
    if platform == 'win32':
        base = Path(environment.get('LOCALAPPDATA') or home / 'AppData/Local')
    elif platform == 'darwin':
        base = home / 'Library/Application Support'
    else:
        candidate = Path(environment.get('XDG_DATA_HOME') or home / '.local/share')
        base = candidate if candidate.is_absolute() else home / '.local/share'
    return (base / 'a_stock_agents').expanduser().resolve()

WORKSPACE_ROOT = default_data_root(PACKAGE_ROOT)
PROJECT_ROOT = WORKSPACE_ROOT  # legacy writable root, never the bundle root

def _runtime_dir(env_name, default_name):
    path=Path(os.environ.get(env_name,default_name)).expanduser()
    return path.resolve() if path.is_absolute() else (WORKSPACE_ROOT/path).resolve()

def get_workspace_env_paths():
    """Return private settings paths in precedence order during root-env migration."""
    local_env = _runtime_dir('A_STOCK_LOCAL_DIR','local') / 'settings' / '.env'
    legacy_env = WORKSPACE_ROOT / '.env'
    return (local_env,) if local_env == legacy_env else (local_env, legacy_env)

def get_workspace_env_path():
    """Return the canonical private settings env file, with a legacy root fallback."""
    paths = get_workspace_env_paths()
    return next((path for path in paths if path.exists()), paths[0])

def load_workspace_env():
    for path in get_workspace_env_paths():
        if path.exists():
            for line in path.read_text(encoding='utf-8-sig').splitlines():
                line=line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key,value=line.split('=',1)
                    os.environ.setdefault(key.strip(),value.strip().strip('"').strip("'"))
load_workspace_env()

OUTPUT_DIR=_runtime_dir('A_STOCK_OUTPUT_DIR','output')
LOG_DIR=_runtime_dir('A_STOCK_LOG_DIR','log')
TEMP_DIR=_runtime_dir('A_STOCK_TEMP_DIR','temp')
LOCAL_DIR=_runtime_dir('A_STOCK_LOCAL_DIR','local')

def bundle_resource(relative):
    path=(PACKAGE_ROOT/relative).resolve()
    if PACKAGE_ROOT not in path.parents: raise ValueError('Bundle resource escapes package')
    return path

def skill_resource(skill_id,relative=''):
    base=(SKILLS_ROOT/skill_id).resolve()
    if base.parent!=SKILLS_ROOT.resolve(): raise ValueError('Invalid skill identifier')
    path=(base/relative).resolve()
    if path!=base and base not in path.parents: raise ValueError('Skill resource escapes skill')
    return path

def enforce_secure_permissions(path):
    if os.name!='nt' and path.exists():
        os.chmod(path,0o700)
        for directory,dirs,files in os.walk(path):
            for name in dirs: os.chmod(Path(directory)/name,0o700)
            for name in files: os.chmod(Path(directory)/name,0o600)

def ensure_workspace_dirs():
    for path in (OUTPUT_DIR,LOG_DIR,TEMP_DIR,LOCAL_DIR): path.mkdir(parents=True,exist_ok=True)
    enforce_secure_permissions(LOCAL_DIR)

def get_log_path(module='app',session_id=None):
    ensure_workspace_dirs()
    directory=LOG_DIR/module
    directory.mkdir(parents=True,exist_ok=True)
    tag=session_id or __import__('datetime').datetime.now().strftime('%Y%m%d')
    return directory/f'{module}-{tag}.log'

def get_temp_path(name='scratch'):
    ensure_workspace_dirs()
    path=(TEMP_DIR/name).resolve()
    if TEMP_DIR.resolve() not in path.parents: raise ValueError('Temporary path escapes workspace')
    path.mkdir(parents=True,exist_ok=True)
    return path

def check_workspace_health():
    found={path.parent.name for path in SKILLS_ROOT.glob('*/SKILL.md')}
    manifest=json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    ids={item['id'] for item in manifest['skills']}
    return {'package_root':str(PACKAGE_ROOT),'workspace_root':str(WORKSPACE_ROOT),'skills_root':str(SKILLS_ROOT),
            'total_skills':len(found),'business_skills':len(ids),'skills_manifest':MANIFEST_PATH.exists(),
            'cli_launcher':(RUNTIME_ROOT/'cli.py').is_file(),
            'is_healthy':len(ids)==6 and found==ids|{'a-stock-agents'} and (RUNTIME_ROOT/'cli.py').is_file()}

if __name__=='__main__': print(json.dumps(check_workspace_health(),ensure_ascii=False,indent=2))
