"""Close remaining path and documentation contracts after the physical migration."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
RUNTIME=ROOT/'skill_bundle/runtime'


def main():
    for p in (ROOT/'tests').rglob('*.py'):
        t=p.read_text(encoding='utf-8')
        t=t.replace('scripts.server.', 'server.')
        t=t.replace('ROOT / "scripts/server"','ROOT / "apps/web-console/backend/server"')
        p.write_text(t,encoding='utf-8')
    p=ROOT/'tests/governance/test_skill_contracts.py';t=p.read_text(encoding='utf-8')
    t=t.replace('ROOT / "web" / "js" / "app.js"','ROOT / "apps/web-console/frontend/js/app.js"')
    # Skill document paths are now scoped to the bundle, not repository root.
    t=t.replace('ROOT / item["skill_doc"]','ROOT / "skill_bundle" / item["skill_doc"]')
    p.write_text(t,encoding='utf-8')
    for name in ['core/paper_trading/a_stocks_backtest.py','core/strategy/portfolio_risk_manager.py']:
        p=RUNTIME/name;t=p.read_text(encoding='utf-8')
        t=t.replace('default_config = PROJECT_ROOT / "config" / "config.yaml"',
                    'from core.config import resolve_config_file\n            default_config = resolve_config_file()')
        p.write_text(t,encoding='utf-8')
    p=RUNTIME/'core/data/data_bridge.py';t=p.read_text(encoding='utf-8')
    t=t.replace('config_path = CONFIG_DIR / "config.yaml"','from core.config import resolve_config_file\n        config_path = resolve_config_file()')
    p.write_text(t,encoding='utf-8')
    p=RUNTIME/'core/data/fetch_realtime.py';t=p.read_text(encoding='utf-8')
    t=t.replace('env_path = Path(__file__).resolve().parents[3] / ".env"',
                'from core.workspace import get_workspace_env_path\n    env_path = get_workspace_env_path()')
    t=t.replace('cfg_path = os.path.join(script_dir, "config.yaml")',
                'cfg_path = LOCAL_DIR / "skills" / "astock-data-feed" / "config.yaml"')
    p.write_text(t,encoding='utf-8')
    p=RUNTIME/'core/config.py';t=p.read_text(encoding='utf-8')
    t=t.replace('        PROJECT_ROOT / "config" / "stock_pools.yaml",\n','')
    p.write_text(t,encoding='utf-8')
    p=RUNTIME/'core/strategy/execution_action_engine.py';t=p.read_text(encoding='utf-8')
    t=t.replace('cfg_files = [CONFIG_DIR / "stock_pools.yaml", PROJECT_ROOT / "config" / "stock_pools.yaml"]',
                'cfg_files = [CONFIG_DIR / "stock_pools.yaml"]')
    p.write_text(t,encoding='utf-8')
    # Importable old pack API forwards to one authoritative archive implementation.
    for name in ['tools/legacy/pack.py','bin/pack.py']:
        (ROOT/name).write_text('from pathlib import Path\nimport sys\nROOT=next(p for p in Path(__file__).resolve().parents if (p/"skill_bundle/bundle.json").exists())\nsys.path.insert(0,str(ROOT))\nfrom tools.packaging.common import package_project, main\nif __name__=="__main__":main()\n',encoding='utf-8')
    (ROOT/'tools/legacy/run_skill.py').write_text('from pathlib import Path\nimport runpy,sys\nroot=Path(__file__).resolve().parents[2]\nsys.path.insert(0,str(root/"skill_bundle/runtime"))\nif __name__=="__main__":runpy.run_path(str(root/"skill_bundle/runtime/run_skill.py"),run_name="__main__")\n',encoding='utf-8')
    p=ROOT/'tools/packaging/common.py';t=p.read_text(encoding='utf-8')
    t=t.replace("'.ps1','.cmd','.sh'", "'.ps1','.cmd','.sh','.svg','.png','.jpg','.jpeg','.woff','.woff2'")
    t=t.replace("('references.py','windows_junction.ps1',platform+'.py')", "('references.py','windows_junction.ps1','host.py',platform+'.py')")
    p.write_text(t,encoding='utf-8')
    p=ROOT/'tools/legacy/update.py';t=p.read_text(encoding='utf-8')
    t=t.replace('PROTECTED_DIRS = [OUTPUT_DIR.name, "output", "user_data", "backups"]',
                'PROTECTED_DIRS = [OUTPUT_DIR.name, "output", "user_data", "backups", "local", "log", "temp", ".agents"]')
    t=t.replace('PROTECTED_FILES = ["config/config.yaml"]','PROTECTED_FILES = [".env", "local/settings/application.yaml"]')
    t=t.replace('PROJECT_ROOT / "config" / "config.yaml"','PROJECT_ROOT / "local" / "settings" / "application.yaml"')
    t=t.replace('".venv", "venv", "backups", "output", "user_data", OUTPUT_DIR.name','".venv", "venv", "backups", "output", "user_data", "local", "log", "temp", ".agents", OUTPUT_DIR.name')
    t=t.replace('str(PROJECT_ROOT / "verify.py")','str(PROJECT_ROOT / "skill_bundle/runtime/doctor.py")')
    p.write_text(t,encoding='utf-8')
    # Document actual authority rather than rewriting immutable audit history.
    for p in [ROOT/'README.md',ROOT/'AGENTS.md']:
        t=p.read_text(encoding='utf-8')
        t=t.replace('scripts/core/workspace.py','skill_bundle/runtime/core/workspace.py')
        t=t.replace('scripts/core/cli.py','skill_bundle/runtime/cli.py')
        t=t.replace('.agents/skills/<skill_id>/SKILL.md','skill_bundle/skills/<skill_id>/SKILL.md')
        p.write_text(t,encoding='utf-8')
    p=ROOT/'AGENTS.md';t=p.read_text(encoding='utf-8')
    t=t.replace('严禁**将本项目的技能或配置复制到系统全局目录','严禁**将本项目的技能或配置复制到系统全局目录')
    notice='''
## 当前源码与接入契约（2026-10-14）

技能唯一来源为 `skill_bundle/skills/`，公共运行时为 `skill_bundle/runtime/core/`；`.agents/skills`仅是本机发现引用。总入口`a-stock-agents`与19项专业技能共20个入口，业务清单仍为19项。

公共配置/模板位于`skill_bundle/assets/`，共用说明位于`skill_bundle/references/`，有效用户配置位于`local/settings/application.yaml`（支持A_STOCK_CONFIG_PATH）。Web应用位于`apps/web-console/`，不得复制公共算法。

路径统一从`core.workspace`导入：PACKAGE_ROOT、RUNTIME_ROOT、SKILLS_ROOT为代码根；WORKSPACE_ROOT为可写根，旧PROJECT_ROOT兼容为WORKSPACE_ROOT。所有output/log/temp/local写入仍通过该接口。禁止用固定父目录层数或链接别名定位公共源码。

项目内引用允许使用经验证的符号链接/Windows junction；失败不复制。用户级引用须属于明确授权的宿主接入任务，不默认创建；链接卸载只能移除入口，不删除目标源码。Windows/macOS/Linux宿主接入分别验收。

'''
    if '## 当前源码与接入契约' not in t:t=t.replace('---',notice+'---',1)
    p.write_text(t,encoding='utf-8')
    p=ROOT/'README.md';t=p.read_text(encoding='utf-8')
    note='''
## 当前工程布局与使用

唯一技能集合为`skill_bundle/`，含`skills/`（总入口+19项专业技能）、`runtime/`、公共`assets/`及`references/`。可选Web前后端位于`apps/web-console/`；根`bin/astock*`保留为薄兼容入口。

AI工具通过从`skill_bundle/`生成的Release使用技能；开发源码不作为项目发现入口。各宿主原生导入与发现能力按平台单独验证。

离线诊断：`python skill_bundle/runtime/doctor.py`。统一CLI：`python skill_bundle/runtime/cli.py <command> --json`。总包分发器：`python skill_bundle/runtime/run_skill.py <skill-id> --params '{"code":"600519"}' --json`。

私有配置保存在`local/settings/`；技能环境变量放在`local/settings/.env`，WebUI开发配置放在`tools/containers/web-console/`。代码升级保留local/output/log/temp。Windows/macOS/Linux真实宿主验收分开记录。

发布归档入口为`tools/packaging/build_codex.py`、`build_hermes.py`、`build_workbuddy.py`，输出到output/packages；归档是完整集合的版本快照，不是强制复制式宿主导入包，也不作为第二套源码维护。

'''
    if '## 当前工程布局与使用' not in t:t=note+t
    t=t.replace('hermes --skills-dir ./.agents/skills','hermes skills trust')
    t=t.replace('python verify.py','python skill_bundle/runtime/doctor.py')
    t=t.replace('根据当前操作系统自适应建立 `.agents/skills` 链接','根据当前操作系统自适应建立指向唯一 `skill_bundle/skills` 的 `.agents/skills` 引用')
    p.write_text(t,encoding='utf-8')
    p=ROOT/'docs/guidelines/engineering/project-structure-specification.md';t=p.read_text(encoding='utf-8')
    t=t.replace('技能代码或环境依赖复制、软链接到操作系统的全局目录','技能代码、配置或环境依赖复制到操作系统的全局目录')
    t=t.replace('核心业务与量化算法统一归集于 `scripts/core/`，Web 服务网关归集于 `scripts/server/`，智能体就地技能存放在 `.agents/skills/`',
                '核心业务与量化算法统一归集于 `skill_bundle/runtime/core/`，Web网关归集于 `apps/web-console/backend/server/`，技能定义存放于 `skill_bundle/skills/`；`.agents/skills`仅为引用入口')
    t=t.replace('彻底根除代码库中的硬编码绝对路径与脆弱的软链接','消除硬编码主机路径和固定父目录层数；发现引用与代码路径解析分离')
    t=t.replace('`Path(__file__).resolve().parents[...]`','`core.workspace`的代码根与工作区接口')
    t=t.replace('目标目录尚未迁移，链接例外须在实施阶段同步修订 AGENTS.md 并验收，不能据此自动创建全局引用',
                '目录与AGENTS.md已按目标迁移；Windows项目引用已建立，三系统真实宿主验收仍待完成，不自动创建全局引用')
    p.write_text(t,encoding='utf-8')
    print('Updated canonical configuration readers, legacy launchers, archive and current documentation')


if __name__=='__main__':main()
