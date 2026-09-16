# Token 配置方案：环境变量或项目 `.env`

## 原则

`scripts/config.yaml` 的 `proxy_patch.auth_token` 保持为空，避免令牌进入技能目录、备份或版本控制。项目技能只在当前工作区内运行，不向用户全局目录复制配置。

## 解析优先级

1. 进程环境变量 `AUTH_TOKEN`。
2. 项目根目录 `.env` 中的 `AUTH_TOKEN=...`（`.gitignore` 已排除）。
3. `scripts/config.yaml` 的空值兼容字段。

## 新机器配置

PowerShell：

```powershell
$env:AUTH_TOKEN = "你的TOKEN"
.\bin\astock.ps1 data quote 600519 --json
```

Bash：

```bash
export AUTH_TOKEN="你的TOKEN"
./bin/astock data quote 600519 --json
```

如需会话间保留，可在项目根目录创建未跟踪的 `.env`，不要把令牌写入技能或系统全局目录。

## 验证

```bash
grep "auth_token" .agents/skills/astock-data-feed/scripts/config.yaml
python scripts/core/cli.py data quote 600519 --json
```

第一条应显示 `auth_token: ""`；第二条应返回结构化 JSON。
