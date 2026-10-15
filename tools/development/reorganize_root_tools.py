"""One-time root-tool migration. No builds, dependency installation or services."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]


def write(relative, content):
    path = ROOT/relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8', newline='\n')


def move(source, target):
    src, dst = ROOT/source, ROOT/target
    assert src.resolve().is_relative_to(ROOT) and dst.resolve().is_relative_to(ROOT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        if dst.exists(): raise RuntimeError(f'Archive already exists: {dst}')
        os.rename(src, dst)


def main():
    move('.dockerignore', 'tools/containers/web-console/Dockerfile.dockerignore')
    move('.design-context.md', 'docs/guidelines/ui/design-context.md')
    docker_ignore = ROOT/'tools/containers/web-console/Dockerfile.dockerignore'
    if docker_ignore.exists():
        text = docker_ignore.read_text(encoding='utf-8').replace('!.env.example\n', '')
        docker_ignore.write_text(text, encoding='utf-8', newline='\n')
    design = ROOT/'docs/guidelines/ui/design-context.md'
    if design.exists():
        text = design.read_text(encoding='utf-8')
        text = text.replace('`web/css/style.css`](file:///Users/handy/workon/a_stock_agents/web/css/style.css)', '`apps/web-console/frontend/css/style.css`](../../../apps/web-console/frontend/css/style.css)')
        text = text.replace('`docs/guidelines/ui/ui-design-guide.md`](file:///Users/handy/workon/a_stock_agents/docs/guidelines/ui/ui-design-guide.md)', '`ui-design-guide.md`](ui-design-guide.md)')
        text = text.replace('`docs/guidelines/ui/market-data-sync-control-console-specification.md`](file:///Users/handy/workon/a_stock_agents/docs/guidelines/ui/market-data-sync-control-console-specification.md)', '`market-data-sync-control-console-specification.md`](market-data-sync-control-console-specification.md)')
        text = text.replace('This context is derived from existing implementation and design docs because no prior `.design-context.md` existed.', 'This is development guidance for the optional WebUI; it is not part of the skill Release.')
        design.write_text(text, encoding='utf-8', newline='\n')
    for filename in ('install.ps1','install.sh','run.ps1','run.sh','update.ps1','update.sh','verify.py'):
        move(filename, 'log/root-tools-migration/retired/'+filename)
    move('tools/legacy/update.py', 'log/root-tools-migration/retired/legacy-update.py')
    for source, target in [('Dockerfile','Dockerfile'),('docker-compose.yml','compose.yaml'),('docker-entrypoint.sh','entrypoint.sh')]:
        move(source, 'tools/containers/web-console/'+target)
    for name, command in [('setup','setup'),('run-web','run-web')]:
        write('tools/development/'+name+'.ps1', f'''$ErrorActionPreference = 'Stop'
$PythonExec = $env:A_STOCK_PYTHON
if (-not $PythonExec) {{
    $TaskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
    $Candidate = Join-Path $TaskRoot '.venv/Scripts/python.exe'
    if (Test-Path -LiteralPath $Candidate) {{ $PythonExec = $Candidate }}
    else {{
        foreach ($Name in @('python3', 'python', 'py')) {{
            if (Get-Command $Name -ErrorAction SilentlyContinue) {{ $PythonExec = $Name; break }}
        }}
    }}
}}
if (-not $PythonExec) {{ throw 'Python 3.9+ required' }}
& $PythonExec (Join-Path $PSScriptRoot 'manage.py') {command} @args
exit $LASTEXITCODE
''')
        write('tools/development/'+name+'.sh', f'''#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
PYTHON_EXEC="${{A_STOCK_PYTHON:-}}"
if [ -z "$PYTHON_EXEC" ]; then
  if [ -x "$SCRIPT_DIR/../../.venv/bin/python" ]; then PYTHON_EXEC="$SCRIPT_DIR/../../.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then PYTHON_EXEC=python3
  else PYTHON_EXEC=python; fi
fi
exec "$PYTHON_EXEC" "$SCRIPT_DIR/manage.py" {command} "$@"
''')
    write('tools/legacy/update.py', '''"""Retired ZIP overlay updater. Never modifies developer source or user data."""
import sys

def apply_update_from_zip(zip_path, backup_dir):
    print('ZIP overlay updates are retired; use Git for source and the host Release update mechanism.', file=sys.stderr)
    return False

def main():
    print('Updater retired. No files changed. Use Git for development; install Releases through the target host.', file=sys.stderr)
    raise SystemExit(2)

if __name__ == '__main__': main()
''')
    write('tools/containers/web-console/Dockerfile', '''# Optional Web-console development/debug image, not a skill Release.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \\
    A_STOCK_WORKSPACE_ROOT=/data \\
    A_STOCK_SERVER_HOST=0.0.0.0 A_STOCK_SERVER_PORT=6300 \\
    PYTHONPATH=/app/skill_bundle/runtime:/app/apps/web-console/backend:/app
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \\
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
ARG PIP_INDEX_URL=""
RUN if [ -n "$PIP_INDEX_URL" ]; then \\
        pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt; \\
    else pip install --no-cache-dir -r requirements.txt; fi
RUN useradd -m -u 1000 -s /bin/bash appuser \\
    && mkdir -p /data/output /data/local /data/log /data/temp \\
    && chown -R appuser:appuser /data /app
COPY --chown=appuser:appuser skill_bundle ./skill_bundle
COPY --chown=appuser:appuser apps/web-console ./apps/web-console
COPY --chown=appuser:appuser tools/containers/web-console/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh
USER appuser
EXPOSE 6300
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \\
    CMD curl -f http://127.0.0.1:6300/api/health || exit 1
ENTRYPOINT ["./entrypoint.sh"]
''')
    write('tools/containers/web-console/compose.yaml', '''# Optional Web debug environment. Invoke explicitly from the development repo.
services:
  web-console:
    build:
      context: ../../..
      dockerfile: tools/containers/web-console/Dockerfile
    image: a-stock-agents-web-dev:local
    restart: "no"
    ports:
      - "127.0.0.1:${A_STOCK_SERVER_PORT:-6300}:6300"
    environment:
      A_STOCK_WORKSPACE_ROOT: /data
      A_STOCK_SERVER_HOST: 0.0.0.0
      A_STOCK_SERVER_PORT: 6300
      # production is the authenticated runtime policy, not a deployment claim.
      A_STOCK_RUNTIME_MODE: production
      A_STOCK_CONFIG_PATH: /data/local/settings/application.yaml
      A_STOCK_OUTPUT_DIR: /data/output
      A_STOCK_LOCAL_DIR: /data/local
      A_STOCK_LOG_DIR: /data/log
      A_STOCK_TEMP_DIR: /data/temp
    env_file:
      - path: ./.env
        required: false
      - path: ../../../local/settings/.env
        required: false
    volumes:
      - ../../../output:/data/output
      - ../../../local:/data/local
      - ../../../log:/data/log
    tmpfs:
      - /data/temp:uid=1000,gid=1000,mode=0700
    extra_hosts:
      - "host.docker.internal:host-gateway"
''')
    write('tools/containers/web-console/entrypoint.sh', '''#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -eq 0 ] || [ "${1:0:1}" = '-' ]; then
    exec python apps/web-console/backend/server/run.py --host "${A_STOCK_SERVER_HOST:-0.0.0.0}" --port "${A_STOCK_SERVER_PORT:-6300}" "$@"
fi
if [ "$1" = "astock" ]; then
    shift
    exec python skill_bundle/runtime/cli.py "$@"
fi
exec "$@"
''')
    write('tools/containers/web-console/.env.example', '''# Optional WebUI development settings.
A_STOCK_SERVER_HOST=127.0.0.1
A_STOCK_SERVER_PORT=6300
A_STOCK_SERVER_RELOAD=false
A_STOCK_RUNTIME_MODE=production

# Set only when the WebUI needs additional browser origins.
# A_STOCK_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Docker Desktop can reach a host Ollama service through this address.
# For local run-web use localhost instead.
# OLLAMA_BASE_URL=http://host.docker.internal:11434
''')
    write('skill_bundle/assets/config/runtime.env.example', '''# Optional private environment settings for skill runtime.
# Copy to local/settings/.env and add credentials there; never put real values in this template.
A_STOCK_OUTPUT_DIR=output
A_STOCK_DEFAULT_MODEL=deepseek-chat
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
OPENAI_API_KEY=
# OPENAI_BASE_URL=https://api.openai.com/v1
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
A_STOCK_LLM_TIMEOUT=60.0
# OLLAMA_BASE_URL=http://localhost:11434
''')
    obsolete_env_example = ROOT/'.env.example'
    if obsolete_env_example.exists(): obsolete_env_example.unlink()
    path = ROOT/'tests/governance/test_security_audit.py'
    text = path.read_text(encoding='utf-8').replace('(PROJECT_ROOT / "docker-compose.yml")','(PROJECT_ROOT / "tools/containers/web-console/compose.yaml")')
    path.write_text(text,encoding='utf-8')
    path = ROOT/'tests/core/test_skill_suite_layout.py'
    text = path.read_text(encoding='utf-8').replace('def test_release_archive_is_generated_without_private_data_or_source_mutation', '@pytest.mark.skipif(__import__("os").environ.get("A_STOCK_NO_BUILD") == "1", reason="User requested no builds, including temporary Release archives")\ndef test_release_archive_is_generated_without_private_data_or_source_mutation')
    path.write_text(text,encoding='utf-8')
    path = ROOT/'README.md'
    text = path.read_text(encoding='utf-8')
    text = text.replace('install.ps1','tools/development/setup.ps1').replace('install.sh','tools/development/setup.sh').replace('run.ps1','tools/development/run-web.ps1').replace('run.sh','tools/development/run-web.sh')
    text = text.replace('docker compose ', 'docker compose -f tools/containers/web-console/compose.yaml ')
    start = text.find('## 六、')
    if start != -1:
        end = text.find('\n## 七、', start)
        if end != -1:
            text = text[:start]+'''## 六、开发源码与Release更新

开发仓库通过Git维护，保留未提交修改；不再用技能ZIP覆盖开发源码。旧update入口已退役并拒绝执行。宿主通过其受支持的Release更新机制管理安装版本，用户数据独立保留。
'''+text[end:]
    text = text.replace('docker-compose.yml','tools/containers/web-console/compose.yaml')
    path.write_text(text,encoding='utf-8')
    path = ROOT/'docs/guidelines/engineering/skill-suite-portability-specification.md'
    text = path.read_text(encoding='utf-8').replace('│   ├── development/                   # 工程迁移工具，不交付','│   ├── development/                   # setup、run-web、迁移工具，不交付\n│   ├── containers/web-console/        # 可选Web调试Docker，不交付').replace('├── install.ps1 / install.sh           # 只初始化开发依赖及诊断\n├── run.ps1 / run.sh                    # 开发 Web 调试入口\n','')
    text += '\n## 7. 开发辅助入口\n\n初始化使用tools/development/setup.ps1或setup.sh；共享manage.py实现依赖选择、失败退出与离线诊断。默认安装test依赖，browser/full显式选择，不自动运行扩展测试。Web通过run-web启动并将输出保存到log/web-console。Docker归属tools/containers/web-console，仓库为context，Dockerfile专用忽略规则放在Dockerfile旁；代码/app和可写数据/data分离，output/local/log持久化，temp用可销毁tmpfs。production保留为鉴权策略标识，不表示开发容器已达到生产部署验收。\n\n旧ZIP覆盖更新入口退役并拒绝调用；开发仓库通过Git维护。离线验证入口为tools/validation/check.py，默认doctor，--core显式选择P0。旧混合verify脚本只保留在迁移日志中供恢复，不作为活跃工具。requirements.txt由tools/development/export_dependencies.py从uv.lock离线导出，不手工维护第二份依赖。\n'
    path.write_text(text,encoding='utf-8')


if __name__ == '__main__': main()
