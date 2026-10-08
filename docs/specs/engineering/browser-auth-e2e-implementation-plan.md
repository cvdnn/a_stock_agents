# 浏览器认证自动化与安全截图实施计划

> **实施状态：** 已完成｜P0、P1、7 例系统 Edge 矩阵与截图目检均通过
> **适用范围：** Web 工作台自动化测试、无头浏览器交互验证、登录后页面截图
> **安全原则：** 不关闭生产鉴权，不增加万能请求头、免登录参数或固定测试密码

**Goal:** 建立一套使用隔离测试配置、临时数据库和真实用户会话的浏览器自动化底座，使工作台可以无人值守完成登录、交互、DOM 审计和截图，同时保证生产认证边界不被削弱。

**Architecture:** 浏览器测试启动独立 Uvicorn 子进程，仅监听回环地址并使用随机端口；测试进程生成临时配置、SQLite 数据库和短生命周期测试账号；浏览器通过真实 `/api/auth/login` 建立会话，再执行工作台验证。默认测试门禁不运行浏览器 E2E，必须通过显式环境开关启用。

**Tech Stack:** Python、FastAPI、SQLite、pytest、Playwright、Microsoft Edge、PowerShell。

---

## 一、现状与问题边界

当前认证体系包含两种凭据：

1. pytest API 测试在临时数据库中签发真实用户会话 Token，并通过共享 `client` fixture 携带凭据；
2. 真实服务 E2E 使用 `A_STOCK_SERVER_TOKEN` 作为机器集成凭据。

机器集成 Token 可以通过外层认证中间件，但不能让 `/api/auth/me` 建立用户和 RBAC 上下文。主页面启动时必须成功调用 `/api/auth/me`，否则认证遮罩不会解除。因此，给无头浏览器添加静态机器 Token 不能替代登录后的工作台验收。

本计划不新增测试专用免认证 API，而是自动建立隔离的真实用户会话。

---

## 二、阶段 0：实施前基线校准

**目标：** 在修改前记录认证、测试和浏览器链路的真实状态。

**检查范围：**

- `scripts/server/app.py`：认证中间件和静态页面挂载；
- `scripts/server/auth/dependencies.py`：会话 Token 与用户上下文解析；
- `scripts/server/api/auth.py`：登录、登出、`/api/auth/me`；
- `tests/conftest.py`：临时数据库和共享认证 fixture；
- `tests/server/test_live_server_e2e.py`：机器 Token E2E；
- `web/index.html`、`web/js/auth.js`：认证遮罩、会话保存和跳转；
- 当前工作区未提交修改，特别是 `tests/conftest.py` 的既有用户改动。

**交付证据：**

- 当前可以自动验证的场景；
- 因 `401` 或缺少用户上下文失败的场景；
- 只能进行静态渲染、不能算作真实工作台验收的场景；
- 实施前相关文件的 diff 摘要。

---

## 三、阶段 1：安全回归测试先行

**目标：** 先建立 RED 测试，防止后续实现通过削弱鉴权来让截图变绿。

**拟新增文件：**

- `tests/server/test_browser_e2e_security.py`
- `tests/browser/conftest.py`
- `tests/browser/test_authenticated_workspace.py`

**必须覆盖的安全断言：**

- [x] 匿名访问受保护 API 返回 `401`；
- [x] 无效或过期会话 Token 返回 `401`；
- [x] 测试模式绑定 `0.0.0.0` 或其他非回环地址时拒绝启动；
- [x] 生产模式不创建测试账号，也不接受任何测试身份配置；
- [x] 浏览器测试只能使用显式临时数据库；
- [x] 测试启动不读取或同步真实 `config/config.yaml` 中的管理员凭据；
- [x] `X-Test-User`、`X-Debug-Admin`、`bypass_auth` 等请求不能获得身份；
- [x] 测试结束后临时会话和数据库不可继续使用；
- [x] 任何失败输出、日志和截图文件名中均不包含密码或 Token。

**禁止实现：**

- 测试专用公开登录绕过端点；
- 万能 Header；
- URL 查询参数免认证；
- 固定万能账号或密码；
- 在生产代码中遇到 `runtime_mode=test` 就跳过认证中间件。

---

## 四、阶段 2：配置与身份隔离

**目标：** 确保浏览器自动化不读取或修改真实用户配置、账号和数据库。

**预计修改文件：**

- `scripts/core/config.py`
- `scripts/server/config.py`
- `scripts/server/db.py`
- `tests/conftest.py`

**实施任务：**

- [x] 增加并统一使用显式 `A_STOCK_CONFIG_PATH`；
- [x] `PROJECT_ROOT_CONFIG()` 使用统一配置路径，不再固定读取生产 `config/config.yaml`；
- [x] 通过 `tmp_path_factory` 为浏览器测试生成临时根目录；
- [x] 在临时根目录中生成最小测试配置、SQLite 数据库和数据同步设置；
- [x] 生成随机测试账号和高强度随机密码；
- [x] 设置短会话 TTL，并在测试结束时撤销或随临时数据库销毁；
- [x] 测试环境变量全部传给独立服务子进程，不修改当前用户的持久环境；
- [x] 配置加载失败时 fail-closed，不回退读取真实用户配置。

**监听安全规则：**

```text
runtime_mode=test
    ├─ host=127.0.0.1 / ::1 → 允许
    └─ 其他监听地址          → 拒绝启动
```

**完成标准：**

- 真实 `config/config.yaml`、默认聊天数据库、持仓池和自选池字节不变；
- 临时测试数据库仅含本轮生成的数据；
- 服务退出后临时凭据不可继续使用。

---

## 五、阶段 3：浏览器自动化底座

**目标：** 使用系统 Edge 完成真实登录并建立可复用的浏览器会话。

**预计修改：**

- `pyproject.toml`：增加独立 `browser-test` 可选依赖；
- 新增 `tests/browser/` 测试基础设施；
- 需要复用时新增 `scripts/tools/browser_e2e.py`。

**自动启动流程：**

1. 申请随机空闲端口；
2. 使用隔离环境变量启动 Uvicorn 子进程；
3. 轮询 `/api/health`，确认服务由本次子进程提供；
4. 启动系统 Microsoft Edge 的无头浏览器上下文；
5. 打开 `/ui/login.html`；
6. 填写本轮临时账号和密码并提交；
7. 等待 `/api/auth/me` 返回 `200`；
8. 确认认证遮罩解除、工作台关键 DOM 出现；
9. 会话仅保存在本轮临时浏览器上下文，不导出可复用凭据文件；
10. 在同一隔离上下文中执行交互、DOM 审计和截图；
11. 在 `finally` 中关闭浏览器和服务进程，清理会话状态及中间文件。

**浏览器就绪条件：**

- 登录页已跳转到 `/ui/`；
- 页面认证 pending 状态解除；
- `/api/auth/me` 成功返回真实测试用户；
- 目标面板关键元素已挂载；
- 没有未允许的 JavaScript 错误；
- 没有意外的 `401`、`403` 或失败 API 请求。

不得使用固定睡眠作为唯一就绪判断。

---

## 六、阶段 4：截图与交互验收场景

### 4.1 认证场景

- [x] 错误密码不能进入工作台；
- [x] 正确登录进入工作台；
- [x] 页面刷新后会话仍然有效；
- [x] 会话失效后工作台恢复登录遮罩；
- [x] 退出登录后 Token 被撤销并返回登录页；
- [x] 匿名访问受保护 API 仍返回 `401`。

### 4.2 工作台场景

- [x] 默认工作台首屏；
- [x] 数据同步控制台；
- [x] 数据同步设置区域；
- [x] 选股工作台的真实空态或真实测试数据态；
- [x] 退出登录后的登录页面。

### 4.3 首批视口

- `1920×1080`：完整桌面验收；
- `1440×900`：常见开发机视口；
- `1280×720`：紧凑桌面边界。

移动端视口作为后续独立扩展，不与首批认证安全改造混在同一批次。

### 4.4 每个场景的证据

- PNG 截图；
- DOM 快照；
- 浏览器控制台错误；
- 失败请求清单；
- 关键元素尺寸和 overflow 检查；
- 当前用户、路径和视口等不含秘密的运行元数据。

动画和 CSS 过渡通过浏览器上下文注入测试样式暂停，不修改生产页面，也不增加公开的 `?test=1` 参数。

---

## 七、阶段 5：运行入口、文档和产物管理

**显式运行入口：**

```powershell
$env:A_STOCK_RUN_BROWSER_E2E = "1"
& .\.venv\Scripts\python.exe -m pytest tests/browser -m browser_e2e
```

默认 pytest 必须跳过浏览器 E2E，并给出明确跳过原因。

**预计更新文档：**

- `tests/README.md`
- `docs/guidelines/engineering/testing-guide.md`
- 浏览器 E2E 故障排查与安全边界说明

**产物落盘规则：**

- `temp/browser-e2e/<run-id>/`：浏览器状态、DOM、中间截图，任务结束后清理；
- `log/browser-e2e/<date>/`：脱敏运行日志；
- `output/reports/`：仅存放用户明确要求保留的最终截图或验收报告。

---

## 八、测试与验收顺序

1. 运行本计划新增的定向 RED 测试，证明旧实现不能满足隔离和自动登录要求；
2. 完成实现后运行相同测试，确认转为 GREEN；
3. 执行 P0 核心门禁：

```powershell
& .\.venv\Scripts\python.exe -m pytest -m core
```

4. 本改动属于服务端 API、配置接线和安全治理的 P1 覆盖面。P0 通过后，先取得人工确认，再执行：

```powershell
& .\.venv\Scripts\python.exe -m pytest -m "core or p1"
```

5. 浏览器 E2E 属 `browser_e2e`、`slow`、`subprocess` 扩展验证，取得人工确认后单独执行；
6. 最后再次执行匿名 `401`、生产模式启动和敏感信息泄漏反向门禁。

静态 HTML 截图不能替代真实登录后的浏览器验收。

---

## 九、最终验收标准

以下条件必须全部满足：

- [x] 浏览器可以无人值守完成真实登录并截取工作台；
- [x] `/api/auth/me` 返回真实测试用户及预期权限上下文；
- [x] 测试账号只拥有场景所需的最小权限；
- [x] 生产模式不存在任何免认证路径；
- [x] 测试服务不能暴露到非回环网卡；
- [x] 真实配置、数据库、股池和持仓文件保持不变；
- [x] 日志、截图、DOM 和 pytest 输出中不存在密码或 Token；
- [x] 匿名访问受保护端点稳定返回 `401`；
- [x] P0 核心门禁零失败（2026-10-08 最终复验：227 passed、337 deselected、52.34s）；
- [x] P1 与浏览器 E2E 的整改后执行结果已在取得确认后单独记录；
- [x] 浏览器失败时保留脱敏证据，成功后自动关闭浏览器/服务进程并销毁临时会话上下文。

---

## 十、提交划分与回滚

建议按以下五个可独立审查的提交实施：

1. `test: lock browser e2e authentication boundaries`
2. `fix: isolate browser e2e config and identity`
3. `test: add authenticated edge automation harness`
4. `test: cover authenticated workspace screenshots`
5. `docs: document secure browser e2e workflow`

**回滚原则：**

- 每阶段可以独立回退；
- 回滚只移除测试基础设施或恢复配置解析逻辑；
- 不删除、移动或覆盖真实用户配置和数据库；
- 不通过保留临时鉴权后门维持旧测试可用性。

---

## 十一、实施记录（2026-10-08）

- 已增加 `A_STOCK_CONFIG_PATH` 与 `A_STOCK_LOCAL_DIR`，使测试配置、聊天库、行情本地库及运行目录可独立隔离；显式 `A_STOCK_DB_PATH` 不再触发旧聊天库迁移。
- 已增加测试模式回环绑定门禁，并接入 `server.run` 与统一 CLI 启动入口；生产监听策略不变。
- 已修复 `web/js/api.js` 对任意非 6300 本机端口强制回指 6300 的问题；仅 3000/5173 前端开发端口继续代理默认后端。
- 已新增伪造身份拒绝、配置/数据库隔离和同源地址 Node 回归测试。
- 已新增 `tests/browser/`：随机回环端口、临时超级管理员引导、场景专用最小权限角色、真实登录、身份核对、DOM overflow 审计及截图证据。
- 已补充 `browser-test` 可选依赖和 `browser_e2e` marker；默认不启动浏览器。
- 已修复两项测试底座问题：Windows `Path` 后缀断言改用 `Path.parts`；workspace/config 的 Windows 判断改用 `os.name`，避免无必要的 WMI 查询。
- 整改后 P0 最终复验通过：227 passed、337 deselected、0 failed，耗时 52.34s；当前总收集 564 例。
- 已补齐隔离 pytest 配置中的随机临时超级管理员凭据，避免治理 API 用例回读真实配置。
- 新增浏览器文件登记治理回归后，`core or p1` 已通过：518 passed、46 deselected、0 failed，耗时 201.53s。
- 已安装项目可选依赖 `playwright==1.63.0`，复用系统 Microsoft Edge，不执行浏览器下载。
- 原 2 例浏览器冒烟结果已作废；当前 7 例系统 Edge 矩阵已通过（557 deselected、0 failed，最终耗时 63.32s），覆盖非回环阻断、三视口、默认/同步设置/选股页面、刷新保持、退出撤销与过期遮罩，并将意外 HTTP ≥400、控制台错误和页面异常设为硬失败。
- 根 pytest 收集钩子已对所有 `browser_e2e` 用例统一实施显式开关；P1 治理用例会扫描所有 `tests/browser/test_*.py`，阻止未登记 `p2 + browser_e2e + slow + subprocess` 的新文件进入仓库。
- 数据同步 API 已统一接入 `require_menu("datasync")`；浏览器测试创建仅含 dashboard、datasync、selection.view/track 的临时角色，普通登录用户无权限时返回 403。
- 浏览器成功后删除含临时密码、SQLite 与 Token 的运行根；失败或显式保留时只复制截图、DOM、审计 JSON 和脱敏日志。
- 失败报告中的运行时对象采用脱敏表示；Windows SQLite 句柄延迟释放使用有上限重试，不能静默跳过清理。
- 截图目检发现并修复选股页收起列 2px 横向溢出及结果卡被属性抽屉挤成竖条的问题；三视口均断言无 overflow、结果区宽度不低于 240px 且上排完整铺满。
- 为既有 `/ui/*` 可访问备份原型补充“非生产设计原型”醒目标识，防止静态假界面被误认为生产能力。
