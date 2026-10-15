"""Finish canonical path wiring without changing business algorithms."""
from pathlib import Path
import os
import re

ROOT=Path(__file__).resolve().parents[2]
RUNTIME=ROOT/'skill_bundle/runtime'


def main():
    for p in (ROOT/'skill_bundle/skills').rglob('*.py'):
        t=p.read_text(encoding='utf-8')
        # Remove continuation lines left by legacy multiline root discovery.
        t=re.sub(r'from core.workspace import PROJECT_ROOT\n\s+parent for parent in Path\(__file__\)\.resolve\(\)\.parents\n\s+if .*\n\)',
                 'from core.workspace import PROJECT_ROOT',t)
        t=t.replace('_target_file = RUNTIME_ROOT / "core" / _rel','_target_file = _AstPath(_core_mod.__file__)')
        if p.name=='a_stocks.py':
            a=t.index('import sys as _astock_sys');b=t.index('from core.cli import main')
            prolog=t[a:t.index('\n\n',t.index('_astock_sys.path.insert',a))]
            t=t[:a]+prolog+'\n\n'+t[b:]
        p.write_text(t,encoding='utf-8')
    # Shared password hashing may be used by persistence without importing the Web app.
    source=ROOT/'apps/web-console/backend/server/auth/crypto.py'
    target=RUNTIME/'core/governance/crypto.py'
    if source.is_file() and not target.exists():os.rename(source,target)
    t=target.read_text(encoding='utf-8').replace('server.db','core.governance.persistence');target.write_text(t,encoding='utf-8')
    source.write_text('import importlib, sys\nsys.modules[__name__] = importlib.import_module("core.governance.crypto")\n',encoding='utf-8')
    p=RUNTIME/'core/governance/persistence.py';t=p.read_text(encoding='utf-8').replace('server.auth.crypto','core.governance.crypto');p.write_text(t,encoding='utf-8')
    p=RUNTIME/'core/cli.py';t=p.read_text(encoding='utf-8');a=t.index('CUR_DIR =');b=t.index('from core.config import (',a)
    t=t[:a]+'''CUR_DIR = Path(__file__).resolve().parent
RUNTIME_ROOT = CUR_DIR.parent
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))
from core.workspace import PROJECT_ROOT
SCRIPTS_DIR = RUNTIME_ROOT

'''+t[b:];p.write_text(t,encoding='utf-8')
    # Canonical module imports for relocated skill regression tests.
    maps={'data_layer':'core.data.data_layer','pv_factors':'core.factors.pv_factors',
          'unstructured_factors':'core.factors.unstructured_factors','factor_synthesizer':'core.factors.factor_synthesizer',
          'risk_position_manager':'core.strategy.risk_position_manager','backtest_engine':'core.backtest.backtest_engine',
          'fundamental_filter':'core.models.fundamental_filter'}
    for p in (ROOT/'tests/skills').rglob('*.py'):
        t=p.read_text(encoding='utf-8')
        for old,new in maps.items():
            # Derive original wrapper module from its source, not guesses.
            candidates=list((ROOT/'skill_bundle/skills').glob('*/scripts/'+old+'.py'))
            if candidates:
                found=re.search(r'^from (core\.[\w.]+) import \*',candidates[0].read_text(encoding='utf-8'),re.M)
                if found:new=found.group(1)
            t=t.replace('from '+old+' import','from '+new+' import')
        p.write_text(t,encoding='utf-8')
    for name in ['run.ps1','run.sh','install.ps1','install.sh','update.ps1','update.sh','verify.py','Dockerfile','docker-entrypoint.sh']:
        p=ROOT/name;t=p.read_text(encoding='utf-8')
        for old,new in [('scripts\\server\\run.py','apps\\web-console\\backend\\server\\run.py'),
                        ('scripts/server/run.py','apps/web-console/backend/server/run.py'),
                        ('scripts/core/cli.py','skill_bundle/runtime/cli.py'),
                        ('scripts\\core\\workspace.py','tools\\host_adapters\\project.py'),
                        ('scripts/core/workspace.py','tools/host_adapters/project.py')]:t=t.replace(old,new)
        t=t.replace('"$ProjectRoot\\scripts;$ProjectRoot;$env:PYTHONPATH"',
                    '"$ProjectRoot\\skill_bundle\\runtime;$ProjectRoot\\apps\\web-console\\backend;$ProjectRoot;$env:PYTHONPATH"')
        t=t.replace('${PROJECT_ROOT}/scripts:${PROJECT_ROOT}:','${PROJECT_ROOT}/skill_bundle/runtime:${PROJECT_ROOT}/apps/web-console/backend:${PROJECT_ROOT}:')
        if name.startswith('install.'):
            t=t.replace('& $VenvPy verify.py','& $VenvPy skill_bundle\\runtime\\doctor.py')
            t=t.replace('"${VENV_PY}" verify.py','"${VENV_PY}" skill_bundle/runtime/doctor.py')
            t=t.replace('全流程验证套件 (verify.py)','离线结构诊断 (doctor.py)')
            t=t.replace('chmod +x bin/astock || true','chmod +x bin/astock skill_bundle/runtime/astock || true')
        if name=='verify.py':
            t=t.replace('PROJECT_ROOT / "scripts"','PROJECT_ROOT / "skill_bundle" / "runtime"')
            t=t.replace('PROJECT_ROOT / "config" / "skills_manifest.json"','PROJECT_ROOT / "skill_bundle/assets/config/skills_manifest.json"')
            t=t.replace('doc_p = PROJECT_ROOT / s["skill_doc"]','doc_p = PROJECT_ROOT / "skill_bundle" / s["skill_doc"]')
        if name=='Dockerfile':
            t=t.replace('PYTHONPATH="/app/scripts:/app"','PYTHONPATH="/app/skill_bundle/runtime:/app/apps/web-console/backend:/app"')
            t=t.replace('COPY --chown=appuser:appuser config ./config\n','')
            t=t.replace('COPY --chown=appuser:appuser scripts ./scripts','COPY --chown=appuser:appuser skill_bundle ./skill_bundle')
            t=t.replace('COPY --chown=appuser:appuser web ./web','COPY --chown=appuser:appuser apps ./apps')
            t=t.replace('COPY --chown=appuser:appuser .agents ./.agents','COPY --chown=appuser:appuser tools ./tools')
        p.write_text(t,encoding='utf-8')
    for p in (ROOT/'tests').rglob('*.py'):
        t=p.read_text(encoding='utf-8')
        t=t.replace('"scripts/server/run.py"','"apps/web-console/backend/server/run.py"')
        t=t.replace("ROOT / 'scripts'", "ROOT / 'skill_bundle' / 'runtime'")
        p.write_text(t,encoding='utf-8')
    print('Repaired multiline roots, shared crypto, launchers and module ownership')


if __name__=='__main__':main()
