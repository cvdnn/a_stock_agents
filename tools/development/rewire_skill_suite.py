"""Rewire moved files to their unique authorities; no mirroring or data deletion."""
from pathlib import Path
import json
import re
import textwrap

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'skill_bundle/runtime'
BACKEND = ROOT / 'apps/web-console/backend'


def write(path, text):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip('\n'), encoding='utf-8')


def update(path, pairs):
    path = ROOT / path
    text = path.read_text(encoding='utf-8-sig')
    for old, new in pairs:
        text = text.replace(old, new)
    path.write_text(text, encoding='utf-8')


def main():
    aliases = {'server.config': 'core.execution.settings', 'server.db': 'core.governance.persistence',
               'server.agent.tools': 'core.execution.tools', 'server.llm': 'core.llm',
               'server.tasks': 'core.jobs', 'server.services.data_sync_settings': 'core.data.user_sync_settings'}
    # Relocate references in maintained code/tests, never traverse user state or discovery links.
    roots = [ROOT/'skill_bundle/runtime', ROOT/'skill_bundle/skills', BACKEND, ROOT/'tools/legacy', ROOT/'tests']
    for scan in roots:
        for p in scan.rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts or p.suffix not in ('.py', '.js'):
                continue
            t = p.read_text(encoding='utf-8-sig')
            t = t.replace('scripts.core.', 'core.')
            if p.is_relative_to(RUNTIME):
                for old, new in aliases.items():
                    t = t.replace(old, new)
            paths = {'scripts/server/agent/tools.py': 'skill_bundle/runtime/core/execution/tools.py',
                     'scripts/server/llm/': 'skill_bundle/runtime/core/llm/',
                     'scripts/server/tasks/': 'skill_bundle/runtime/core/jobs/',
                     'scripts/server/': 'apps/web-console/backend/server/',
                     'scripts/core/': 'skill_bundle/runtime/core/',
                     'scripts/tools/': 'tools/legacy/',
                     'config/skills_manifest.json': 'skill_bundle/assets/config/skills_manifest.json'}
            if ROOT/'tests' in p.parents:
                for old, new in paths.items(): t = t.replace(old, new)
                t = t.replace('"web/', '"apps/web-console/frontend/').replace("'web/", "'apps/web-console/frontend/")
                t = t.replace('/ "web"', '/ "apps" / "web-console" / "frontend"')
                t = t.replace("/ 'web'", "/ 'apps' / 'web-console' / 'frontend'")
                t = t.replace('/ "scripts" / "core"', '/ "skill_bundle" / "runtime" / "core"')
                t = t.replace('/ "scripts" / "server"', '/ "apps" / "web-console" / "backend" / "server"')
                t = t.replace('/ "config" / "skills_manifest.json"', '/ "skill_bundle" / "assets" / "config" / "skills_manifest.json"')
                t = t.replace('/ ".agents" / "skills"', '/ "skill_bundle" / "skills"')
            if p.suffix == '.py':
                t = t.replace('PROJECT_ROOT / "scripts"', 'PROJECT_ROOT / "skill_bundle" / "runtime"')
                t = t.replace('_ROOT / "scripts"', '_ROOT / "skill_bundle" / "runtime"')
                t = t.replace('ROOT / "scripts"', 'ROOT / "skill_bundle" / "runtime"')
            p.write_text(t, encoding='utf-8')
    for name in ('execution', 'jobs'):
        (RUNTIME/'core'/name).mkdir(exist_ok=True)
        init=RUNTIME/'core'/name/'__init__.py'
        if not init.exists(): init.write_text('',encoding='utf-8')

    write('skill_bundle/runtime/core/workspace.py', '''
        """Unique code roots and separately bound writable workspace."""
        from __future__ import annotations
        import json
        import os
        from pathlib import Path
        from typing import Any, Dict, Tuple

        PACKAGE_ROOT = Path(__file__).resolve().parents[2]
        RUNTIME_ROOT = PACKAGE_ROOT / 'runtime'
        SKILLS_ROOT = PACKAGE_ROOT / 'skills'
        ASSETS_ROOT = PACKAGE_ROOT / 'assets'
        REFERENCES_ROOT = PACKAGE_ROOT / 'references'
        MANIFEST_PATH = ASSETS_ROOT / 'config' / 'skills_manifest.json'
        WORKSPACE_ROOT = Path(os.environ.get('A_STOCK_WORKSPACE_ROOT') or os.environ.get('A_STOCK_AGENTS_ROOT') or PACKAGE_ROOT.parent).expanduser().resolve()
        PROJECT_ROOT = WORKSPACE_ROOT  # legacy writable root, never the bundle root

        def _runtime_dir(env_name, default_name):
            path=Path(os.environ.get(env_name,default_name)).expanduser()
            return path.resolve() if path.is_absolute() else (WORKSPACE_ROOT/path).resolve()

        def get_workspace_env_paths():
            local_env = _runtime_dir('A_STOCK_LOCAL_DIR','local') / 'settings' / '.env'
            legacy_env = WORKSPACE_ROOT / '.env'
            return (local_env,) if local_env == legacy_env else (local_env, legacy_env)

        def get_workspace_env_path():
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

        def setup_workspace_mount():
            import importlib.util
            adapter=WORKSPACE_ROOT/'tools/host_adapters/references.py'
            if not adapter.exists(): return False,'Project adapter unavailable; register SKILLS_ROOT directly'
            spec=importlib.util.spec_from_file_location('astock_references',adapter)
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            result=module.register_reference(SKILLS_ROOT,WORKSPACE_ROOT/'.agents/skills')
            return result['status']=='success',result.get('message',result['status'])

        def check_workspace_health():
            found={path.parent.name for path in SKILLS_ROOT.glob('*/SKILL.md')}
            manifest=json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
            ids={item['id'] for item in manifest['skills']}
            return {'package_root':str(PACKAGE_ROOT),'workspace_root':str(WORKSPACE_ROOT),'skills_root':str(SKILLS_ROOT),
                    'total_skills':len(found),'business_skills':len(ids),'skills_manifest':MANIFEST_PATH.exists(),
                    'agents_skills_mounted':(WORKSPACE_ROOT/'.agents/skills').resolve()==SKILLS_ROOT.resolve(),
                    'cli_launcher':(RUNTIME_ROOT/'cli.py').is_file(),
                    'is_healthy':len(ids)==19 and found==ids|{'a-stock-agents'} and (RUNTIME_ROOT/'cli.py').is_file()}

        if __name__=='__main__': print(json.dumps(check_workspace_health(),ensure_ascii=False,indent=2))
    ''')
    # Configure assets and private settings via canonical paths.
    p=RUNTIME/'core/config.py';t=p.read_text(encoding='utf-8')
    a=t.index('# 1. Resolve Project Root');b=t.index('def resolve_config_file',a)
    t=t[:a]+'''from core.workspace import (PROJECT_ROOT, PACKAGE_ROOT, WORKSPACE_ROOT, RUNTIME_ROOT,
                            SKILLS_ROOT, ASSETS_ROOT, REFERENCES_ROOT, LOCAL_DIR, MANIFEST_PATH)
CONFIG_DIR = ASSETS_ROOT / "config"


'''+t[b:]
    t=t.replace('(CONFIG_DIR / "config.yaml").resolve()', '(LOCAL_DIR / "settings" / "application.yaml").resolve()')
    a=t.index('SKILLS_DIR =');b=t.index('def load_config()',a)
    t=t[:a]+'''SKILLS_DIR = SKILLS_ROOT
DOCS_DIR = WORKSPACE_ROOT / "docs"
PROMPTS_DIR = REFERENCES_ROOT / "prompts"
BIN_DIR = RUNTIME_ROOT
SCRIPTS_DIR = RUNTIME_ROOT


'''+t[b:];p.write_text(t,encoding='utf-8')
    update('skill_bundle/runtime/core/governance/skill_registry.py',[
        ('from core.config import PROJECT_ROOT, get_logger','from core.config import PROJECT_ROOT, get_logger\nfrom core.workspace import MANIFEST_PATH'),
        ('MANIFEST_PATH = PROJECT_ROOT / "config" / "skills_manifest.json"','')])
    update('skill_bundle/runtime/core/strategy/stock_funnel.py',[
        ('from core.workspace import OUTPUT_DIR, PROJECT_ROOT','from core.workspace import OUTPUT_DIR, PROJECT_ROOT, ASSETS_ROOT'),
        ('PROJECT_ROOT / "config" / "funnel_strategy.yaml"','ASSETS_ROOT / "config" / "funnel_strategy.yaml"')])
    p=RUNTIME/'core/strategy/chenxiaoqun.py';t=p.read_text(encoding='utf-8')
    a=t.index('# 动态寻找项目根目录');b=t.index('try:',a)
    t=t[:a]+'from core.workspace import PROJECT_ROOT, RUNTIME_ROOT\n\n'+t[b:];p.write_text(t,encoding='utf-8')
    p=RUNTIME/'core/commands/strategy_cmds.py';t=p.read_text(encoding='utf-8')
    a=t.index('    import sys\n',t.index('def cmd_chenxiaoqun'));b=t.index('    code =',a)
    t=t[:a]+'    from core.strategy.chenxiaoqun import ChenXiaoqunStrategyEngine\n\n'+t[b:];p.write_text(t,encoding='utf-8')
    p=RUNTIME/'core/execution/tools.py';t=p.read_text(encoding='utf-8')
    a=t.index('        import sys',t.index('def _sync_astock_strategy_chenxiaoqun'));b=t.index('        result =',a)
    t=t[:a]+'        from core.strategy.chenxiaoqun import ChenXiaoqunStrategyEngine\n\n'+t[b:];p.write_text(t,encoding='utf-8')
    p=RUNTIME/'core/reporting/report_generator.py';t=p.read_text(encoding='utf-8')
    a=t.index('def _resolve_template_path');b=t.index('\n\nTEMPLATE_PATH',a)
    t=t[:a]+'''def _resolve_template_path() -> Path:
    from core.workspace import ASSETS_ROOT
    return ASSETS_ROOT / "templates" / "stock-report.html"
'''+t[b:];p.write_text(t,encoding='utf-8')
    # Web legacy imports are aliases of shared modules, not source copies.
    simple={'config':'core.execution.settings','db':'core.governance.persistence',
            'agent/tools':'core.execution.tools','services/data_sync_settings':'core.data.user_sync_settings'}
    for name,target in simple.items():
        write('apps/web-console/backend/server/'+name+'.py',f'import importlib, sys\nsys.modules[__name__] = importlib.import_module("{target}")\n')
    for oldpkg,newpkg in [('llm','core.llm'),('tasks','core.jobs')]:
        for source in (RUNTIME/newpkg.replace('.','/')).glob('*.py'):
            module=newpkg if source.stem=='__init__' else newpkg+'.'+source.stem
            write('apps/web-console/backend/server/'+oldpkg+'/'+source.name,
                  f'import importlib, sys\nsys.modules[__name__] = importlib.import_module("{module}")\n')
    update('apps/web-console/backend/server/app.py',[
        ('web_dir = Path(__file__).resolve().parent.parent.parent / "web"',
         'web_dir = Path(__file__).resolve().parents[2] / "frontend"')])
    update('apps/web-console/backend/server/run.py',[
        ('for p in [PROJECT_ROOT, SCRIPTS_DIR]:',
         'for p in [PROJECT_ROOT, SCRIPTS_DIR, Path(__file__).resolve().parent.parent]:')])
    # Canonical skill wrapper bootstrap: locate the bundle marker, not arbitrary project roots.
    prolog='''import sys as _astock_sys
import os as _astock_os
import json as _astock_json
from pathlib import Path as _AstPath

def _astock_resolve_bundle():
    _file_path = _AstPath(__file__).resolve()
    # 1. 自定位：自身及父目录向上查找 bundle.json
    for _p in _file_path.parents:
        if (_p / "bundle.json").is_file():
            return _p
    # 2. 兄弟定位：查找兄弟目录 a-stock-agents/bundle.json（未解析/已解析上级均探测）
    for _base in (_AstPath(__file__), _file_path):
        for _p in _base.parents:
            for _candidate in (_p / "a-stock-agents", _p.parent / "a-stock-agents"):
                if (_candidate / "bundle.json").is_file():
                    return _candidate.resolve()
    # 3. 收据定位：读取系统固定安装收据 install.json
    _receipts = []
    _env_root = _astock_os.environ.get("A_STOCK_WORKSPACE_ROOT") or _astock_os.environ.get("A_STOCK_AGENTS_ROOT")
    if _env_root:
        _receipts.append(_AstPath(_env_root) / "install.json")
    if _astock_sys.platform == "win32":
        _local = _astock_os.environ.get("LOCALAPPDATA") or (_AstPath.home() / "AppData/Local")
        _receipts.append(_AstPath(_local) / "a_stock_agents" / "install.json")
    elif _astock_sys.platform == "darwin":
        _receipts.append(_AstPath.home() / "Library/Application Support" / "a_stock_agents" / "install.json")
    else:
        _xdg = _astock_os.environ.get("XDG_DATA_HOME") or (_AstPath.home() / ".local/share")
        _receipts.append(_AstPath(_xdg) / "a_stock_agents" / "install.json")
    for _rp in _receipts:
        if _rp.is_file():
            try:
                _data = _astock_json.loads(_rp.read_text(encoding="utf-8"))
                _target = _data.get("bundle_root") or _data.get("runtime_root") or _data.get("anchor_root")
                if _target:
                    _tp = _AstPath(_target).resolve()
                    if (_tp / "bundle.json").is_file():
                        return _tp
                    if (_tp / "a-stock-agents" / "bundle.json").is_file():
                        return (_tp / "a-stock-agents").resolve()
                    if _tp.name == "runtime" and (_tp.parent / "bundle.json").is_file():
                        return _tp.parent
            except Exception:
                pass
    raise RuntimeError("ANCHOR_SKILL_MISSING: Complete a_stock_agents bundle or a-stock-agents anchor skill required")

_astock_bundle = _astock_resolve_bundle()
_astock_runtime = _astock_bundle / "runtime"
if str(_astock_runtime) not in _astock_sys.path:
    _astock_sys.path.insert(0, str(_astock_runtime))
'''
    for p in (ROOT/'skill_bundle/skills').rglob('*.py'):
        t=p.read_text(encoding='utf-8-sig')
        if 'SSOT) forwarding wrapper' in t or 'Delegates to core.' in t:
            start=t.index('import sys');end=t.index('import core.',start)
            t=t[:start]+prolog+'from core.workspace import PROJECT_ROOT, RUNTIME_ROOT\n_ROOT = PROJECT_ROOT\n\n'+t[end:]
            t=re.sub(r'        _target_file = .*', '        _target_file = RUNTIME_ROOT / "core" / _rel',t)
        else:
            lines=t.splitlines(keepends=True)
            idx=next((i+1 for i,l in enumerate(lines) if l.startswith('from __future__ import')),None)
            if idx is None:
                import ast
                tree=ast.parse(t)
                first=tree.body[0] if tree.body else None
                idx=first.end_lineno if first and isinstance(first,ast.Expr) and isinstance(first.value,ast.Constant) and isinstance(first.value.value,str) else 0
                if idx==0 and lines and lines[0].startswith('#!'):idx=1
            lines.insert(idx,'\n'+prolog+'\n');t=''.join(lines)
            t=re.sub(r'^PROJECT_ROOT = .+$','from core.workspace import PROJECT_ROOT',t,flags=re.M)
        p.write_text(t,encoding='utf-8')
    write('skill_bundle/skills/astock-strategy-chenxiaoqun/scripts/chenxiaoqun_check.py',
          prolog+'from core.strategy.chenxiaoqun import *\nif __name__ == "__main__":\n    main()\n')
    # Manifest paths are bundle-relative and typed; no duplicated active manifest.
    p=ROOT/'skill_bundle/assets/config/skills_manifest.json';data=json.loads(p.read_text(encoding='utf-8'))
    for item in data['skills']:
        item['skill_doc']='skills/'+item['id']+'/SKILL.md'
        entry=item.get('entry_point','')
        if entry.startswith('core/'):
            item['entry_point']='runtime/'+entry
        elif entry.startswith('.agents/skills/'):
            item['entry_point']=entry.replace('.agents/skills/','skills/',1)
        if item['id']=='astock-strategy-chenxiaoqun':item['entry_point']='runtime/core/strategy/chenxiaoqun.py'
        item['execution']={'type':'cli','command':item['cli_command'],'root':'bundle'}
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # Engineering and tests load the unique runtime plus the optional backend.
    update('pyproject.toml',[
        ('where = ["scripts"]','where = ["skill_bundle/runtime", "apps/web-console/backend"]'),
        ('include = ["core*", "server*", "tools*"]','include = ["core*", "server*"]'),
        ('pythonpath = ["scripts", "."]','pythonpath = ["skill_bundle/runtime", "apps/web-console/backend", "."]'),
        ('testpaths = ["tests", ".agents/skills"]','testpaths = ["tests", "skill_bundle/skills"]')])
    update('tests/conftest.py', [('for p in [ROOT, SCRIPTS, SCRIPTS / "core", ROOT / "core"]:',
                                'for p in [ROOT, SCRIPTS, ROOT / "apps/web-console/backend", SCRIPTS / "core"]:')])
    print('Rewired unique runtime, private configuration, skill wrappers and test paths')


if __name__=='__main__': main()
