# 智能选股工作区 R0 基线（2026-10-08）

关联：[修复计划](selection-workbench-remediation-plan.md)。本轮只取证。隔离服务使用 6311 端口、临时 SQLite 和独立模型仓库，未读取或修改用户模型。

## R0-1 服务与脚本

| 项目 | 实测 |
|---|---|
| 工作区 | HEAD a4d5d30a3ed241b644ae789d100a91dd74ddabdc，提交于 2026-10-08 12:28 +0800；取证前工作树干净 |
| 6300 进程 | Uvicorn PID 35032，子 Python PID 2472/24252；命令指向本工作区 .venv 和 server.app:app，监听 127.0.0.1:6300；启动于 2026-10-05 22:38 +0800 |
| 健康 | GET /api/health → HTTP 200，status=ok，version=3.0.0，db_connected=true |
| 匿名认证 | GET /api/selection-models/types → HTTP 401，unauthorized |
| 静态脚本 | GET /ui/ → HTTP 200，引用 js/app.js?v=20261005-1 与 js/selection-models/index.js?v=20261007-1 |

进程启动早于当前 HEAD，未启用 reload。健康接口没有 Git SHA，故无法精确确认 Python 进程加载的提交及当时未提交改动；静态脚本从磁盘读取，不能证明后台版本。后续代码验收须记录新服务启动时的提交。

## R0-2 隔离身份与模型

隔离模型：管理员创建 condition_tree sm_20261008123816，作者创建 funnel sm_20261008123816_1。下表为 2026-10-08 12:38 +0800 的 API 实测。200/error 指 HTTP 200 包装业务错误，不表示动作成功。

| 动作 | 未登录 | 只读 researcher | 模型作者 | 管理员 |
|---|:---:|:---:|:---:|:---:|
| 列表、详情 | 401 | 200/ok | 200/ok | 200/ok |
| 创建 | 401 | 403 | 200/ok | 200/ok |
| 发布、激活 | 401 | 403 | 403 | 200/ok |
| 手工运行 | 401 | 403 | 200/MODEL_VERSION_NOT_FOUND（测量时未激活） | 200/MODEL_DATA_MISSING（缺本地水位） |
| 调试 | 401 | 403 | 403 | 200/MODEL_CONFIG_INVALID（不存在阶段） |
| 不存在的 run_id | 401 | 200/MODEL_RUN_NOT_FOUND | 200/MODEL_RUN_NOT_FOUND | 200/MODEL_RUN_NOT_FOUND |

浏览器匿名进入主页面出现“登录已超时”；只读身份登录后打开选股页，模型列表显示 Failed to fetch，但“＋新建”“发布”“调试”“停止运行”仍可点击。直接 HTTP 请求同端口 API 成功，因此本次浏览器请求失败不能直接归因于选股 API。web/js/api.js:5-7 会将非 6300 端口的 localhost/127.0.0.1 页面请求指向 6300。作者和管理员的浏览器页面交互尚未可靠验证。

## R0-3 失败映射与逐项复测

| 现象 | 代码入口 | 后续复测 |
|---|---|---|
| 401/403 使用 HTTP detail，业务错误使用 HTTP 200 + status=error | scripts/server/app.py、scripts/server/auth/dependencies.py、web/js/api.js:19-27 | R1-3：真实错误文案和按钮权限状态 |
| 旧内存工作台与新模块并存 | web/js/app.js:11386-11559、web/js/selection-models/index.js:184-186 | R1-2：刷新、搜索、切页只由 SelModels 处理 |
| 漏斗保存读取不存在的 def.__draft_revision | web/js/selection-models/funnel_editor.js:85 | R2-1：连续保存、刷新、冲突 |
| 添加规则均用 rules.push | condition_editor.js:68、funnel_editor.js:62 | R2-2：原位编辑、新建追加、ID 冲突 |
| 尚无真实运行记录验证详情/节点/候选归属 | scripts/server/api/selection_models.py:793-826 | R1-1、R3：两个隔离 run_id 的详情、节点、候选、导出 |
| 作者对管理员模型的运行通过权限门才返回业务错误；停止按钮总可见 | selection_models.py:712-793,833-844、web/index.html:1003 | R4-1、R4-4：所有权与可取消实例 |
| 隔离浏览器 Failed to fetch，但同端口 API 直连成功 | web/js/api.js:5-27、selection-models/index.js:27-45 | 解决独立源地址，再测四角色页面与浏览器网络错误 |

以下为首轮结论；后续补充验证已建立新进程版本证据并完成四身份浏览器取证。旧 6300 进程的精确加载提交仍不可追溯。

## 补充验证（2026-10-08 15:54～16:18 +0800）

本轮以当前 HEAD `a4d5d30a3ed241b644ae789d100a91dd74ddabdc` 启动独立进程，选股仓库、SQLite、缓存、股池与锁均指向 `temp/selection-r0-verify/`。6311 进程 PID 12196（16:00:59 启动），6312 进程 PID 38364（16:12:51 启动）；均由工作区 `.venv/Scripts/python.exe temp/r0_verify_server.py` 启动，后者通过 `R0_PORT=6312` 指定端口。6311 的 `/api/health` 为 HTTP 200，6312 的浏览器选股 API 为 HTTP 200；启动清单记录了 HEAD、工作树状态、隔离路径、脚本 SHA-256 与服务 API SHA-256。旧 6300 进程的精确加载提交仍未知。

浏览器同源验证使用**仅存在于临时服务的** `/ui/js/api.js` 覆盖路由，把原脚本中非 6300 页面跳转到 6300 的地址改为空字符串；产品文件 `web/js/api.js` 未改。浏览器网络事件显示刷新后 `/api/selection-models`、详情、版本、运行、调度、结果和数据健康请求均发送到 `http://localhost:6312`，响应 HTTP 200；服务访问日志与目标一致。6311 的登录、`/api/auth/me` 和选股请求也由同一隔离端口处理。首次挂载路径写成 `/js/api.js` 时，仍加载原 `/ui/js/api.js` 并复现 `Failed to fetch`；修正挂载路径后列表正常加载。故独立端口仍需正式修复地址接线，临时覆盖只用于验证选股工作台。

隔离浏览器与服务日志对应如下。所有模型 ID 均位于隔离仓库，未读取或修改用户原有模型：

| 身份 | 浏览器现象与关键动作 | 隔离服务响应 |
|---|---|---|
| 未登录 | 主页面提示“登录已超时” | `/api/auth/me` 401；选股接口匿名 401 已在上节记录 |
| researcher | 登录后选股列表正常显示；顶栏“新建模型”禁用，但列表“＋新建”和“发布”仍可点击 | `/api/auth/me` 200；对隔离模型 `sm_20261008155457` 发布 POST 403，模型未发布 |
| model_author | 登录后创建 `sm_20261008160824`，保存草稿；发布提示 `[object Object]`，手工运行先提示已发起、随后提示“尚未激活任何版本” | 创建 POST 200、草稿 PATCH 200、发布 POST 403、运行 POST HTTP 200 业务错误 `MODEL_VERSION_NOT_FOUND` |
| super_admin | 登录后选中 `sm_20261008155456`，校验通过，发布 v1 并激活；手工运行提示“本地数据水位未就绪”；调试阶段入口提示“需要 stage_id 或 stage 之一” | 校验、发布、激活均 HTTP 200/ok；运行和调试均 HTTP 200 包装业务错误，不产生正式候选 |

`/api/auth/me` 在四类会话中分别返回匿名 401 或登录 200；浏览器显示的用户分别为 R0-researcher、R0-model_author、R0-super_admin。401/403 是 HTTP 鉴权拒绝，未激活版本、缺水位和缺调试阶段是 HTTP 200 的业务错误。发布 403 被页面渲染为 `[object Object]`，而运行按钮先显示“已发起”再显示失败，均是后续 R1/R4 的具体复测对象。浏览器首次加载顺序为 `/api/auth/me` → 选股类型/规则类型 → 列表 → 模型详情/版本 → 结果/调度/运行/数据健康；模型切换先请求详情，再请求其版本、调度、运行和结果。

补充验证使用了本地临时服务及测试身份；没有在真实用户模型上执行创建、发布、激活、运行或调试。隔离进程在取证后已停止，临时资产按工作区三目录规范清理。

## 测试门禁记录

首次按工作区规则运行 .venv/Scripts/python.exe -m pytest -m core：收集 547 例，547 例全部 deselected，0 selected。原因是 tests/conftest.py 的档位表使用正斜杠，而 Windows 返回的相对路径含反斜杠；本次已把路径归一化为 POSIX 形式。再次运行同一 P0 命令时，pytest 在收集阶段触发 Windows fatal exception 0x8007000e，堆栈位于 Python platform._wmi_query，未得到用例结果；测试进程已停止。P0 状态为“未完成”，不能报告通过。没有执行 P1、全量、network 或 live 测试。

补充验证再次运行 `.venv/Scripts/python.exe -m pytest -m core`：收集 547 例，320 deselected、**227 selected**，先前的 0 选中和 `0x8007000e` 未重现。进度到 44% 时 `tests/core/test_selection_data_and_scheduling.py` 出现 1 个失败，按“失败即止”立即中断，未得到完整通过数。按该文件测试顺序，失败位置疑似 `test_canonical_paths_follow_ssot_1310`：其中两处用 Windows 的 `str(Path)` 对比带正斜杠的后缀；因中断前未输出 traceback，此定位为待核实推断。P0 当前为**失败，不能标记通过**；没有执行 P1、全量、network 或 live。
