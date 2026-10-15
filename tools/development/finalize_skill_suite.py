"""Finalize resource ownership and thin compatibility launchers after move-only migration."""
from pathlib import Path
import json
import os
import re
import sys
import textwrap

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'))
import yaml


def write(name,text):
    path=ROOT/name
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip('\n'),encoding='utf-8')


def main():
    skills=ROOT/'skill_bundle/skills'
    write('skill_bundle/skills/a-stock-agents/SKILL.md','''
        ---
        name: a-stock-agents
        description: A股技能总入口。用于行情、选股、持仓风控、模拟盘、报告及多空辩论；按需求路由到同集合的19项专业技能，以确定性程序计算。
        compatibility: Requires complete a_stock_agents bundle, Python 3.9+ and dependencies. Supports Windows, macOS and Linux.
        metadata:
          product: a_stock_agents
          version: "3.0.0"
        ---

        # A-Stock Agents 总入口

        本技能只负责导航与自身编排，不保存公共引擎。读取集合的references/execution-contract.md和assets/config/skills_manifest.json，按需读取skills/<id>/SKILL.md。

        从本文件真实路径定位带bundle.json的集合根。程序经runtime/bootstrap.py与core.workspace定位，Windows调用runtime/astock.ps1，macOS/Linux调用runtime/astock；所有正式调用追加--json。

        空股池停止分析并提示登记；数据不足或能力未实现必须如实返回原因。持仓建议包含精确保本价、三级风控及三场景动作。单项技能不能脱离完整集合独立安装；宿主强制复制时使用项目显式调用。
    ''')
    write('skill_bundle/references/execution-contract.md','''
        # 共享执行契约

        集合由bundle.json标识，skills/runtime/assets/references完整交付。统一执行：Python运行runtime/cli.py <command> --json；基础技能不依赖Web。

        A_STOCK_WORKSPACE_ROOT绑定用户工作区；旧A_STOCK_AGENTS_ROOT兼容为工作区。默认集合父目录。用户有效配置位于local/settings/application.yaml，可由A_STOCK_CONFIG_PATH显式指定，不回退其他实例。

        代码与资源根由模块真实路径和集合标识定位，不依赖当前目录或链接别名。output是最终交付物，log是审计，temp是可重建暂存，local是私有状态。升级不替换用户状态。

        项目发现入口仅引用skills目录；链接失败不复制。20个入口包含总入口与19项专业技能，真实宿主发现数另行验证。
    ''')
    relocation={}
    def move(source,target):
        source,target=Path(source),Path(target)
        assert ROOT in source.resolve().parents and ROOT in target.resolve().parents
        if target.exists():raise FileExistsError(target)
        target.parent.mkdir(parents=True,exist_ok=True)
        os.rename(source,target)
        relocation[str(source.resolve())]=target
    for skill in skills.iterdir():
        if not skill.is_dir():continue
        for name,new in [('templates','assets/templates'),('data','assets/examples'),('api-reference','references/api-reference')]:
            source=skill/name
            if source.is_dir():move(source,skill/new)
        # Move runtime settings, never publish account or proxy credentials.
        for source in [skill/'config.yaml',skill/'scripts/config.yaml']:
            if source.is_file():move(source,ROOT/'local/skills'/skill.name/'config.yaml')
        # Move skill-local regression and smoke tools out of production resources.
        for p in list((skill/'scripts').glob('*.py')) if (skill/'scripts').is_dir() else []:
            if p.name.startswith('test_'):
                # strip production-only bootstrap; pytest supplies canonical import paths.
                t=p.read_text(encoding='utf-8')
                start=t.find('import sys as _astock_sys')
                if start>=0:
                    end=t.find('\n\n',t.find('_astock_sys.path.insert',start))
                    if end>=0:t=t[:start]+t[end+2:]
                p.write_text(t,encoding='utf-8')
                move(p,ROOT/'tests/skills'/skill.name/p.name)
            elif p.name in {'full_function_smoke_check.py','real_stock_rule_validation.py','rule_regression_check.py','backtest_batch_validation.py'}:
                move(p,ROOT/'tools/validation'/skill.name/p.name)
    source=skills/'astock-data-feed/assets/templates/stock-report.html'
    if source.exists():move(source,ROOT/'skill_bundle/assets/templates/stock-report.html')
    sample=skills/'astock-screener-5a/scripts/sh000001_klines.json'
    if sample.exists():move(sample,ROOT/'output/cache/migration/sh000001_klines.json')
    # Forward legacy module names, never duplicate shared implementation.
    for pkg,target in [('llm','core.llm'),('tasks','core.jobs')]:
        write('apps/web-console/backend/server/'+pkg+'/__init__.py',f'from {target} import *\n')
    write('bin/astock.ps1','''
        & (Join-Path $PSScriptRoot '../skill_bundle/runtime/astock.ps1') @args
        exit $LASTEXITCODE
    ''')
    write('bin/astock.cmd','''
        @echo off
        call "%~dp0..\\skill_bundle\\runtime\\astock.cmd" %*
        exit /b %ERRORLEVEL%
    ''')
    write('bin/astock','''
        #!/usr/bin/env bash
        set -e
        ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
        exec bash "$ROOT/skill_bundle/runtime/astock" "$@"
    ''')
    for name,entry in [('pack','tools/legacy/pack.py'),('update','tools/legacy/update.py'),('run_skill','skill_bundle/runtime/run_skill.py')]:
        write('bin/'+name+'.py',f'''from pathlib import Path
import runpy,sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/"skill_bundle/runtime"))
runpy.run_path(str(root/"{entry}"),run_name="__main__")
''')
    # Resolve skill settings through their owner, not source-relative configuration copies.
    for p in skills.rglob('*.py'):
        t=p.read_text(encoding='utf-8')
        if 'PROJECT_ROOT / "config" / "stock_pools.yaml"' in t:
            t=t.replace('PROJECT_ROOT / "config" / "stock_pools.yaml"','_astock_bundle / "assets" / "config" / "stock_pools.yaml"')
        t=t.replace('PROJECT_ROOT / ".agents" / "skills"','_astock_bundle / "skills"')
        t=t.replace('SCRIPT_DIR.parent / "config" / "pools.yaml"','_astock_bundle / "assets" / "config" / "stock_pools.yaml"')
        if p.name in ('fetch_patched.py','_init_patch.py'):
            t=t.replace('os.path.join(script_dir, "config.yaml")','str(__import__("core.workspace",fromlist=["LOCAL_DIR"]).LOCAL_DIR / "skills" / "astock-data-feed" / "config.yaml")')
        p.write_text(t,encoding='utf-8')
    # Normalize portable front matter. Extension properties belong in string metadata.
    for p in skills.glob('*/SKILL.md'):
        t=p.read_text(encoding='utf-8');_,head,body=t.split('---',2);fm=yaml.safe_load(head)
        metadata=fm.get('metadata') or {}
        flat={str(k):str(v) if isinstance(v,(str,int,float)) else json.dumps(v,ensure_ascii=False) for k,v in metadata.items()}
        for k in list(fm):
            if k not in {'name','description','license','compatibility','metadata','allowed-tools'}:
                value=fm.pop(k);flat[k]=str(value) if isinstance(value,(str,int,float)) else json.dumps(value,ensure_ascii=False)
        fm['metadata']=flat
        fm.setdefault('compatibility','Requires the complete a_stock_agents bundle and Python 3.9+; shared runtime is not bundled per skill.')
        p.write_text('---\n'+yaml.safe_dump(fm,allow_unicode=True,sort_keys=False)+'---'+body,encoding='utf-8')
    # Repair relative documentation links using old physical roots and moved resource ownership.
    prefixes=[('.agents/skills/','skill_bundle/skills/'),('.agents/prompts/','skill_bundle/references/prompts/'),
              ('scripts/core/','skill_bundle/runtime/core/'),('scripts/server/','apps/web-console/backend/server/'),
              ('web/','apps/web-console/frontend/'),('config/','skill_bundle/assets/config/')]
    for p in list(skills.rglob('*.md'))+list((ROOT/'docs').rglob('*.md'))+[ROOT/'README.md',ROOT/'AGENTS.md']:
        t=p.read_text(encoding='utf-8')
        if skills in p.parents:
            olddoc=ROOT/'.agents/skills'/p.relative_to(skills)
            rel=str(p.relative_to(ROOT))
            for src,dst in relocation.items():
                if Path(dst) in p.parents:
                    olddoc=Path(src)/p.relative_to(dst)
                    olddoc=ROOT/'.agents/skills'/olddoc.relative_to(skills)
                    break
        else:olddoc=p
        def href(match):
            value=match.group(1);parts=value.split('#',1);target=parts[0]
            if not target or re.match(r'^[a-z]+:',target):return match.group(0)
            absolute=(olddoc.parent/target).resolve()
            if ROOT not in absolute.parents:return match.group(0)
            rel=absolute.relative_to(ROOT).as_posix()
            candidate=absolute
            for old,new in prefixes:
                if rel.startswith(old):candidate=ROOT/(new+rel[len(old):]);break
            for old,new in relocation.items():
                base=Path(old)
                if candidate==base:candidate=new;break
                if base in candidate.parents:candidate=new/candidate.relative_to(base);break
            if candidate.exists():
                return ']('+Path(os.path.relpath(candidate,p.parent)).as_posix()+('#'+parts[1] if len(parts)>1 else '')+')'
            return match.group(0)
        t=re.sub(r'\]\(([^)]+)\)',href,t)
        if skills in p.parents:
            t=t.replace('.agents/skills/','skill_bundle/skills/').replace('scripts/core/','skill_bundle/runtime/core/')
        p.write_text(t,encoding='utf-8')
    for p in [ROOT/'skill_bundle/runtime/astock',ROOT/'bin/astock']:
        p.chmod(p.stat().st_mode|0o111)
    print('Finalized resource owners, 20 portable skill documents, launchers and relative links')


if __name__=='__main__':main()
