# Token 配置方案：~/.AI-Platform/.env

## 背景

`scripts/config.yaml` 原有的 `proxy_patch.auth_token` 字段明文存储代理网关令牌。
该文件位于 skill 目录下，若被共享、备份、提交到 Git，token 即泄露。

**已迁出到 `~/.AI-Platform/.env`，config.yaml 中 `auth_token` 已清空。**

## 当前方案（2026-07-15 最终落地）

### 文件布局

| 文件 | 内容 | 职责 |
|------|------|------|
| `~/.AI-Platform/.env` | `AUTH_TOKEN=***` | 唯一 Token 存储点 |
| `scripts/config.yaml` | `auth_token: ""` | 已清空（向后兼容兜底） |
| `scripts/_init_patch.py` | 解析 `.env` 回退 config.yaml | Token 读取逻辑 |
| `scripts/fetch_patched.py` | 同上 + 余额预检 | Token 读取 + 余额检查 |

### Token 解析优先级

```
1. ~/.AI-Platform/.env -> AUTH_TOKEN= 行           推荐（唯一入口）
2. config.yaml -> proxy_patch.auth_token      向后兼容（已清空）
```

### 标准读取模式

```python
from pathlib import Path

env_path = Path.home() / ".AI-Platform" / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("AUTH_TOKEN="):
            auth_token = line.split("=", 1)[1].strip().strip("\"'")
else:
    cfg = yaml.safe_load(open(config_path))
    auth_token = cfg["proxy_patch"].get("auth_token", "")
```

## 在新机器部署

```bash
echo 'AUTH_TOKEN=你的TOKEN' > ~/.AI-Platform/.env
```

无需修改 `.bashrc`、无需设置环境变量。所有脚本自动读取。

## 与旧方案的差异

| 维度 | 旧方案（.bashrc + os.environ） | 新方案（~/.AI-Platform/.env） |
|------|:-------------------------------:|:------------------------:|
| 存储位置 | Shell 配置文件，随 Shell 状态变化 | 独立文件，AI-Platform 平台无关 |
| 读取方式 | `os.environ.get("AUTH_TOKEN")` | 显式文件解析 |
| Shell 依赖 | 需要 `source ~/.bashrc` | 无 |
| 权限管理 | 与 .bashrc 同级 | 可独立设置 600 |

## 验证方法

```bash
# 1. 确认 config.yaml 无明文 token
grep "auth_token" ./.AI-Platform/skills/stocks/a-share-data/scripts/config.yaml
# 输出应为: auth_token: ""

# 2. 确认 .env 文件存在且格式正确
cat ~/.AI-Platform/.env
# 输出: AUTH_TOKEN=20260616...

# 3. 全链路测试（无需 AUTH_TOKEN 环境变量）
VENV_PY="/path/to/venv/bin/python3"
SKILL_DIR="./.AI-Platform/skills/stocks/a-share-data/scripts"
$VENV_PY "$SKILL_DIR/fetch_patched.py" fetch_realtime.py --quote 600519 --json
# 应正常返回实时行情
```
