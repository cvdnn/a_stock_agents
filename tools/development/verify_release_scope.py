"""Build candidates and verify them outside the development tree.

DEPRECATION NOTICE (2026-10-15, P0-06):
    本脚本此前包含会修改开发源码树的行为（写入 setup.sh/SKILL.md/.gitignore）。
    核心隔离构建与解压验收断言已迁移至标准常驻门禁：
    `tests/core/test_release_delivery_gate.py::test_isolated_extraction_and_doctor_smoke_across_platforms`
    本脚本现转为只读的候选验证辅助工具，严禁执行源码树覆写。
"""
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
    # 2026-10-15 (P0-06): 移除会覆写 setup.sh、SKILL.md、.gitignore 的破坏性逻辑。
    # 验收断言已由 tests/core/test_release_delivery_gate.py 接管并常驻化。
    archive=ROOT/'log/skill-suite-migration/retired-setup'
    archive.mkdir(parents=True,exist_ok=True)
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
