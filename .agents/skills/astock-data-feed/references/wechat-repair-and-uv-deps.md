# WeChat 重连 & uv 依赖管理

## 问题：WeChat iLink 会话过期（session timeout / errcode=-14）

Gateway 日志中可见：
```
[Weixin] Session expired; pausing for 10 minutes
[Weixin] send chunk failed to=...: iLink sendmessage error errcode=-14 errmsg=session timeout
```

### 原因

AI-Platform WeChat 集成使用 Tencent iLink 平台（ilinkai.weixin.qq.com），通过 bot 账号（xxx@im.bot）转发消息。iLink 登录凭证有时效限制，过期后需要重新认证。

### 诊断命令

```bash
AI-Platform send --list                    # 检查 WeChat 目标是否存在
AI-Platform send --to "weixin:o9cq80_44-iOfvA2ypn-wDE5YJms@im.wechat" "test"  # 测试发送
grep -i "session\|timeout\|weixin" ~/.AI-Platform/logs/gateway.log | tail -20   # 查看日志
```

### 修复步骤

**关键**：`AI-Platform gateway restart` **不能修复** — 问题是 iLink 服务端 token 已失效，需要重新获取凭证。

#### 方法 A：交互式重配（推荐）

1. **先装依赖到 uv 环境**（AI-Platform 的 Python 与系统隔离）：

```bash
uv tool install --reinstall AI-Platform --with qrcode --with aiohttp --with cryptography
```

> AI-Platform 通过 `uv tool install` 安装，其 Python 在 `~/.local/share/uv/tools/AI-Platform/bin/python3`。
> `--with` 在重装时附加额外包。验证：`~/.local/share/uv/tools/AI-Platform/bin/python3 -c "import qrcode; print('ok')"`

2. **启动交互式配置**：

```bash
AI-Platform gateway setup
```

TUI 导航：
- 方向键到 "Weixin / WeChat (configured)" → **回车**
- **Reconfigure? [y/N]** → 输入 `y` + 回车
- **Start QR login? [Y/n]** → 输入 `Y` + 回车
- 终端显示二维码 → **手机微信扫码**
- DM 授权：回车默认 / 群聊：回车默认 / 设 home channel：回车默认
- 最后重启 Gateway：**Y**

3. **验证**：

```bash
AI-Platform send --to "weixin:<chat_id>" "测试消息"
# → 应返回 "Sent to weixin home channel"
```

#### 方法 B：iLink 后台手动换 Token

1. 浏览器打开 https://ilinkai.weixin.qq.com
2. 登录你的 WeChat bot 账号，获取新 token
3. 更新 `~/.AI-Platform/.env` 中的 `WEIXIN_TOKEN`
4. `AI-Platform gateway restart`

#### 二维码渲染失败的处理

若报 `No module named 'qrcode'`：
1. 根本修复：`uv tool install --reinstall AI-Platform --with qrcode`
2. 临时方案：终端会输出 URL，在手机浏览器打开即可扫码，**不需要重开流程**
