# Token 配置方案：环境变量或项目 `.env`

## 原则

兼容回退文件 `local/skills/astock-data-feed/config.yaml`（位于工作区数据根，非集合目录）的 `proxy_patch.auth_token` 保持为空，避免令牌进入技能目录、备份或版本控制。技能目录不保存任何用户配置，也不向用户全局目录复制配置。

## 解析优先级

1. 进程环境变量 `AUTH_TOKEN`。
2. 用户工作区 `local/settings/.env` 中的 `AUTH_TOKEN=...`（`local/` 已排除在版本控制和Release之外）。
3. 工作区 `local/skills/astock-data-feed/config.yaml` 的空值兼容字段。

## 新机器配置

PowerShell：

```powershell
$env:AUTH_TOKEN = "你的TOKEN"
& "$BUNDLE/runtime/astock.ps1" data quote 600519 --json
```

Bash：

```bash
export AUTH_TOKEN="你的TOKEN"
"$BUNDLE/runtime/astock" data quote 600519 --json
```

如需会话间保留，可在用户工作区 `local/settings/.env` 保存令牌，不要把令牌写入技能源码或系统全局目录。

## 验证

```bash
"$BUNDLE/runtime/astock" data quote 600519 --json
```

应返回结构化 JSON；若提示未找到 `AUTH_TOKEN`，按上方优先级补充配置。工作区内如存在 `local/skills/astock-data-feed/config.yaml`，其 `auth_token` 应保持为空。
