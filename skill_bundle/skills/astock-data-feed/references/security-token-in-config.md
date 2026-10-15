# Token 配置方案：环境变量或项目 `.env`

## 原则

`scripts/config.yaml` 的 `proxy_patch.auth_token` 保持为空，避免令牌进入技能目录、备份或版本控制。项目技能只在当前工作区内运行，不向用户全局目录复制配置。

## 解析优先级

1. 进程环境变量 `AUTH_TOKEN`。
2. 用户工作区 `local/settings/.env` 中的 `AUTH_TOKEN=...`（`local/` 已排除在版本控制和Release之外）。
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

如需会话间保留，可在用户工作区 `local/settings/.env` 保存令牌，不要把令牌写入技能源码或系统全局目录。

## 验证

```bash
grep "auth_token" skill_bundle/skills/astock-data-feed/scripts/config.yaml
python skill_bundle/runtime/core/cli.py data quote 600519 --json
```

第一条应显示 `auth_token: ""`；第二条应返回结构化 JSON。
