"""Build candidates and verify them outside the development tree."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[2]


def main():
    # Retire setup scripts that wrote skill-local config or used removed paths.
    archive=ROOT/'log/skill-suite-migration/retired-setup'
    archive.mkdir(parents=True,exist_ok=True)
    for skill in ('astock-data-feed','astock-platform-evaluate'):
        path=ROOT/'skill_bundle/skills'/skill/'setup.sh'
        backup=archive/(skill+'.sh')
        if not backup.exists():backup.write_bytes(path.read_bytes())
        path.write_text('''#!/usr/bin/env bash
set -euo pipefail
BUNDLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while [ ! -f "$BUNDLE_ROOT/bundle.json" ]; do
  PARENT="$(dirname "$BUNDLE_ROOT")"
  if [ "$PARENT" = "$BUNDLE_ROOT" ]; then echo "Complete A-Stock bundle required" >&2; exit 1; fi
  BUNDLE_ROOT="$PARENT"
done
PYTHON_EXEC="${A_STOCK_PYTHON:-python3}"
exec "$PYTHON_EXEC" "$BUNDLE_ROOT/runtime/doctor.py"
''',encoding='utf-8',newline='\n')
    doc=ROOT/'skill_bundle/skills/a-stock-agents/SKILL.md'
    doc.write_text(doc.read_text(encoding='utf-8').replace('宿主强制复制时使用项目显式调用','宿主安装使用完整Release；开发仓库不作为项目发现模式'),encoding='utf-8')
    ignore=ROOT/'.gitignore'
    ignore.write_text(ignore.read_text(encoding='utf-8'),encoding='utf-8',newline='\n')
    sys.path.insert(0,str(ROOT))
    from tools.packaging.common import package_project
    records=[]
    (ROOT/'temp').mkdir(exist_ok=True)
    for platform in ('codex','hermes','workbuddy'):
        path=package_project(ROOT/'output/packages'/f'a_stock_agents_v3_{platform}.zip',platform=platform)
        with tempfile.TemporaryDirectory(prefix='release-proof-',dir=ROOT/'temp') as scratch:
            extracted=Path(scratch)/'install'
            with zipfile.ZipFile(path) as zipped:
                assert all(not Path(name).is_absolute() and '..' not in Path(name).parts for name in zipped.namelist())
                assert len([name for name in zipped.namelist() if name.endswith('/SKILL.md')])==20
                zipped.extractall(extracted)
            env=os.environ.copy()
            env['A_STOCK_WORKSPACE_ROOT']=str(Path(scratch)/'private')
            env['PYTHONPATH']=''
            for key in ('A_STOCK_OUTPUT_DIR','A_STOCK_LOG_DIR','A_STOCK_TEMP_DIR','A_STOCK_LOCAL_DIR','A_STOCK_CONFIG_PATH'):
                env.pop(key,None)
            result=subprocess.run([sys.executable,str(extracted/'skill_bundle/runtime/doctor.py')],cwd=scratch,env=env,capture_output=True,text=True,check=True)
            health=json.loads(result.stdout)
            assert health['is_healthy'] and health['total_skills']==20,health
            records.append({'platform':platform,'archive':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'isolated_doctor':True,'skills':20,'native_host_verified':False})
    evidence=ROOT/'log/skill-suite-migration/release-scope-proof.json'
    evidence.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(records,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
