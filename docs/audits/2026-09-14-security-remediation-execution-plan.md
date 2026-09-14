# A-Stock Agents 生产安全漏洞整改实施执行计划

> **规范指引**：本计划基于系统安全扫描分析报告制定，覆盖项目中的全部高、中、低危安全隐患。分阶段实施、步骤以 `- [ ]` 跟踪，保证每个阶段可独立构建、独立测试与验证。

- **制定日期**：2026-09-14
- **基准版本**：生产当前分支
- **状态**：待执行 (Pending Approval)

---

## 一、范围与架构决策 (Scope & Architecture Decisions)

| 决策点 | 方案选择 | 理由与权衡 |
| :--- | :--- | :--- |
| **文档读写安全边界** | 强制沙箱落盘在 `output/reports` | 禁止外部参数指定目录穿透至 `web/`、`config/` 或 `scripts/`，杜绝文件篡改 |
| **iframe 交互隔离** | 剥离 `allow-same-origin` | 遵循 W3C 标准，禁止同源 iframe 访问宿主 DOM/Cookie，消除报告 XSS 逃逸 |
| **Markdown 事件过滤** | 禁用 `onclick`，改用事件委托 | DOMPurify 严格净化所有原生事件监听器，避免 Prompt 注入诱发任意脚本执行 |
| **外部通信 SSRF** | DNS 物理 IP 前置解析 + 私网拦截 | 拦截所有动态域名（如 `nip.io`）解析至私有网段/云元数据地址，保护内网资产 |
| **API 身份认证** | 引入可选 `A_STOCK_SERVER_TOKEN` 中间件 | 生产与多机环境强制 Bearer Token，单机开发环境免密兼容，容器默认绑定 `127.0.0.1` |
| **数据库密钥静态加密** | 基于密钥混淆加密 `llm_providers.api_key` | 避免 SQLite 数据库文件外泄导致第三方 API Key 全量暴露 |

---

## 二、整改实施里程碑与详细任务

### 🚩 里程碑 0: 阻断高危破坏与沙箱逃逸 (P0 - 预计 1 人日)

#### 1. 修复 `/api/docs/save` 工作区任意文件覆写 (SEC-01)
- [ ] **目标文件**：`scripts/server/app.py`
- [ ] **实施步骤**：
  1. 约束保存根路径：强制锁定至 `(workspace_root / "output" / "reports").resolve()`。
  2. 剥离输入路径中的目录部分，仅提取合法文件名 `Path(req.path.strip()).name`。
  3. 拦截任何尝试写入 `web/index.html`、`config/*`、`scripts/*` 的请求并抛出 HTTP 403 Forbidden。
  4. 保持合法 HTML 与 Markdown 研报交付物的自动归档和生成功能不受影响。

#### 2. 修正 iframe 沙箱同源隔离破坏 (SEC-03)
- [ ] **目标文件**：`web/index.html`
- [ ] **实施步骤**：
  1. 定位第 542 行 `<iframe id="workspaceHtmlFrame">`。
  2. 将 `sandbox="allow-scripts allow-same-origin allow-popups"` 修改为 `sandbox="allow-scripts allow-popups allow-forms"`。
  3. 验证去除 `allow-same-origin` 后，ECharts / 报告内部交互正常运作，但无法获取 `window.parent.document`。

#### 3. 修复 DOMPurify 清洗放行 `onclick` 与脆弱正则兜底 (SEC-04)
- [ ] **目标文件**：`web/js/chat_presentation.js`
- [ ] **实施步骤**：
  1. 修改 `sanitizeHtmlOutput`：移除 `ADD_ATTR` 白名单中的 `'onclick'`。
  2. 对前端快捷操作按钮（如实战动作单、查看详情），改用 `data-action` 属性并使用事件监听委托。
  3. 修改未加载 DOMPurify 时的 fallback 分支：直接采用 `escapeHtml` 纯文本转义，移除容易被绕过的脆弱黑名单正则。

#### 4. 修复 `/api/docs/read` 跨目录源码与敏感文件读取 (SEC-06)
- [ ] **目标文件**：`scripts/server/app.py`
- [ ] **实施步骤**：
  1. 从 `allowed_exts` 中彻底删除 `.py` 格式。
  2. 限制读取目标目录范围：只允许读取 `output/`、`reports/`、`docs/` 及 `.agents/skills/**/SKILL.md`。
  3. 对读取 `scripts/`、`tests/`、`.git/`、`.env` 的请求直接拒绝。

#### 5. 报告生成引擎输出路径沙箱化 (SEC-08)
- [ ] **目标文件**：`scripts/server/agent/tools.py`, `scripts/core/reporting/report_generator.py`
- [ ] **实施步骤**：
  1. 在 `generate_simple_report(data, output_path)` 中对 `output_path` 实施约束：若传入了自定义路径，仅提取文件名拼接至 `OUTPUT_REPORTS_DIR`。
  2. 杜绝通过工具调用或任务调度接口传入绝对路径将文件写入系统目录。

---

### 🚩 里程碑 1: 边界收敛与网络加固 (P1 - 预计 1.5 人日)

#### 6. Docker 端口绑定收敛与轻量 API 认证中间件 (SEC-02)
- [ ] **目标文件**：`docker-compose.yml`, `scripts/server/config.py`, `scripts/server/app.py`
- [ ] **实施步骤**：
  1. 修改 `docker-compose.yml`：将 `ports` 改为 `"127.0.0.1:${A_STOCK_SERVER_PORT:-6300}:6300"`。
  2. `ServerSettings` 增加配置：`api_token: Optional[str] = Field(default=None)`，支持环境变量 `A_STOCK_SERVER_TOKEN`。
  3. 在 `create_app()` 中增加鉴权中间件：当 `api_token` 被设置时，验证请求头 `Authorization: Bearer <TOKEN>`；除健康检查 `/api/health` 与静态 UI 资源外，未授权请求均返回 401。

#### 7. 模型测试接口 DNS 级别 SSRF 拦截 (SEC-05)
- [ ] **目标文件**：`scripts/server/api/models_mgmt.py`
- [ ] **实施步骤**：
  1. 引入物理 DNS 解析：在发起 HTTP 请求前调用 `socket.getaddrinfo(hostname, None)` 获取解析后的所有 IP。
  2. 遍历检查所有解析出的 IP，命中任何 `is_private`、`is_loopback`、`is_link_local`、`is_reserved` 时抛出 HTTP 400。
  3. 增加受控开发例外开关：仅当配置明确允许本地连接时（如检测本地 Ollama 服务），且目标端口为 11434 时方可放行。

---

### 🚩 里程碑 2: 凭据静态加密与自动化测试验证 (P2 - 预计 1 人日)

#### 8. SQLite 数据库 API Key 本地混淆与静态加密 (SEC-07)
- [ ] **目标文件**：`scripts/server/db.py`
- [ ] **实施步骤**：
  1. 在 `save_provider` 与 `get_provider_by_id` 中封装对称加解密转换逻辑。
  2. 密钥派生：基于环境变量 `A_STOCK_SECRET_KEY` 或本地机器指纹动态派生。
  3. 数据库落盘 `llm_providers.api_key` 为密文字符串，向外组装 HTTP 请求头时在内存中实时解密。

#### 9. 安全自动化回归测试套件 (TEST)
- [ ] **目标文件**：`tests/test_security_audit.py`
- [ ] **实施步骤**：
  1. 编写文档路径穿越拦截测试（`test_docs_save_path_traversal`, `test_docs_read_denies_py`）。
  2. 编写 SSRF 拦截测试（`test_ssrf_rejects_dns_rebind`, `test_ssrf_rejects_private_ips`）。
  3. 编写 Token 鉴权中间件测试（`test_auth_middleware_flow`）。
  4. 编写 iframe 与 DOMPurify 净化规则测试。

---

## 三、验收标准与验证命令 (Acceptance Criteria)

1. **安全自动化测试全数通过**：
   ```powershell
   pytest tests/test_security_audit.py -v
   ```
2. **系统既有全链路功能回归通过**：
   ```powershell
   python verify.py
   ```
3. **前端交互与报告体验无衰减**：
   - 研报渲染与 ECharts 图表在无 `allow-same-origin` 沙箱下正常展示。
   - 对话流式推送与操作单响应时间不受影响。
