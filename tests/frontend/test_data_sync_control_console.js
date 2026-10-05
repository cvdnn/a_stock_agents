const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.join(__dirname, '../..');
const html = fs.readFileSync(path.join(root, 'web/index.html'), 'utf8');
const css = fs.readFileSync(path.join(root, 'web/css/style.css'), 'utf8');
const app = fs.readFileSync(path.join(root, 'web/js/app.js'), 'utf8');
const apiSource = fs.readFileSync(path.join(root, 'web/js/api.js'), 'utf8');

const results = [];

async function test(name, fn) {
  try {
    await fn();
    results.push({ name, ok: true });
    console.log(`PASS: ${name}`);
  } catch (error) {
    results.push({ name, ok: false, error });
    console.error(`FAIL: ${name}\n  ${error.message}`);
  }
}

function loadAPI(fetchImpl) {
  const sandbox = {
    window: { location: { hostname: 'localhost', port: '6300' } },
    fetch: fetchImpl,
    console,
  };
  vm.createContext(sandbox);
  vm.runInContext(apiSource, sandbox);
  return sandbox.window.AStockAPI;
}

function jsonResponse(data) {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    async json() { return data; },
  };
}

(async () => {
  await test('matrix 1: semantic three-tab workspace is AI-isolated', () => {
    assert.match(html, /id="datasyncTabList"[^>]*role="tablist"/);
    for (const tab of ['run', 'tasks', 'settings']) {
      assert.match(html, new RegExp(`id="datasync-tab-${tab}"[^>]*role="tab"`));
      assert.match(html, new RegExp(`id="datasync-panel-${tab}"[^>]*role="tabpanel"`));
    }
    assert.doesNotMatch(html, /id="pane-datasync"[^>]*style="[^"]*display\s*:\s*none/i, 'active pane must not be hidden inline');
    assert.match(app, /tabId === ['"]datasync['"][\s\S]{0,1200}btnCopilotLauncher[\s\S]{0,300}display\s*=\s*['"]none['"]/);
    assert.match(
      app,
      /tabId\s*!==\s*['"]datasync['"](?:\s*&&\s*tabId\s*!==\s*['"][a-z-]+['"])*\s*&&\s*chatMessages/,
      'datasync must not render hidden chat welcome content',
    );
    assert.match(
      app,
      /tabId\s*!==\s*['"]system['"]\s*&&\s*chatMessages/,
      'system (standalone console) must not render hidden chat welcome content',
    );
    const copilotConfig = app.slice(app.indexOf('const TabCopilotConfigs'), app.indexOf('function getWelcomeMessageHtml'));
    assert.strictEqual(/['"]datasync['"]\s*:/.test(copilotConfig), false, 'datasync must not have an AI copilot config');
  });

  await test('matrix 2: run, task and settings layouts are responsive and accessible', () => {
    for (const selector of [
      '.datasync-console',
      '.datasync-tabs',
      '.datasync-run-layout',
      '.datasync-task-layout',
      '.datasync-settings-layout',
      '.datasync-tab:focus-visible',
    ]) {
      assert.ok(css.includes(selector), `missing ${selector}`);
    }
    assert.match(css, /@media\s*\([^)]*max-width[^)]*\)[\s\S]*\.datasync-(run|task|settings)-layout/);
    assert.match(css, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);
    assert.ok(html.includes('id="datasyncStatusGrid"'), 'run page must include four status cards');
    assert.ok(html.includes('id="datasyncSettingsDomains"'), 'settings page must include domain navigation');
    assert.match(css, /\.datasync-run-layout\.active\s*\{[\s\S]{0,260}grid-template-columns\s*:\s*minmax\(0,\s*1fr\)\s+290px/);
    assert.match(css, /\.datasync-settings-layout\.active\s*\{[\s\S]{0,260}grid-template-columns/);
  });

  await test('matrix 2b: sticky data sync tabs have an opaque page-matched background', () => {
    const override = css.match(/body\.datasync-no-copilot \.datasync-tabs\s*\{([^}]*)\}/)?.[1] || '';
    assert.match(override, /background\s*:\s*var\(--bg-canvas\)/i,
      'sticky data sync tabs must mask scrolling content with the shared canvas background');
    assert.doesNotMatch(override, /background\s*:\s*transparent\b/i,
      'sticky data sync tabs must not allow scrolling content to show through');
  });

  await test('matrix 2c: data update actions use polished accessible button states', () => {
    const base = css.match(/\.datasync-console \.btn-link-xs\s*\{([^}]*)\}/)?.[1] || '';
    assert.match(base, /appearance\s*:\s*none/i, 'action buttons must not fall back to native browser chrome');
    assert.match(base, /display\s*:\s*inline-flex/i, 'action button content must align consistently');
    assert.match(base, /min-height\s*:\s*32px/i, 'compact desktop actions need a stable hit area');
    assert.match(base, /border-radius\s*:\s*6px/i, 'action buttons must use the console radius');
    assert.match(base, /cursor\s*:\s*pointer/i, 'action buttons must advertise clickability');
    assert.match(css, /\.datasync-console \.btn-link-xs:hover\s*\{[^}]*background\s*:/i,
      'action buttons need a visible hover state');
    assert.match(css, /\.datasync-console \.btn-link-xs:active\s*\{[^}]*background\s*:/i,
      'action buttons need a visible pressed state');
    assert.match(css, /\.datasync-console \.btn-link-xs:disabled\s*\{[^}]*cursor\s*:\s*not-allowed/i,
      'disabled actions must be visibly non-interactive');

    const rowAction = css.match(/\.datasync-coverage-table \[data-health-action\]\s*\{([^}]*)\}/)?.[1] || '';
    assert.match(rowAction, /min-width\s*:\s*60px/i, 'row update buttons need a consistent width');
    assert.match(rowAction, /border-color\s*:/i, 'row update buttons need a clear boundary');
    assert.match(rowAction, /background\s*:/i, 'row update buttons need a deliberate surface');
    assert.match(css, /@media\s*\(pointer:\s*coarse\)[\s\S]*?\.datasync-console \.btn-link-xs\s*\{[^}]*min-height\s*:\s*44px/i,
      'touch devices need a 44px minimum action target');
  });

  await test('matrix 3: task transport supports create, list, detail and cancellation', async () => {
    const calls = [];
    const api = loadAPI(async (url, options = {}) => {
      calls.push({ url, options });
      return jsonResponse(url.endsWith('/api/tasks') ? [] : { task_id: 'task_1' });
    });

    await api.createTask({ task_type: 'data_sync', params: { tier: 'P0' } });
    await api.listTasks({ limit: 30 });
    await api.getTask('task_1');
    await api.cancelTask('task_1');

    assert.deepStrictEqual(calls.map((item) => item.options.method || 'GET'), ['POST', 'GET', 'GET', 'DELETE']);
    assert.ok(calls[0].url.endsWith('/api/tasks'));
    assert.strictEqual(JSON.parse(calls[0].options.body).task_type, 'data_sync');
    assert.ok(calls[1].url.endsWith('/api/tasks?limit=30'));
    assert.ok(calls[2].url.endsWith('/api/tasks/task_1'));
    assert.ok(calls[3].url.endsWith('/api/tasks/task_1'));
    assert.match(app, /task_type\s*:\s*taskType/);
    assert.match(app, /task\.task_type\s*===\s*['"]data_sync_batch['"]/);
    assert.match(app, /api\.getTask\s*\(/, 'task selection must load the latest task detail');
    assert.match(app, /total_requested/);
    assert.match(app, /success_count/);
    assert.match(app, /failed_count/);
    assert.match(app, /function\s+datasyncEffectiveStatus\s*\(/, 'partial failures need an effective degraded status');
    assert.match(app, /failed_count[\s\S]{0,240}>\s*0[\s\S]{0,180}['"]degraded['"]/, 'completed tasks with failed items must be degraded');
    assert.match(app, /if\s*\(\s*!taskId\s*\)\s*throw/);
    assert.match(app, /status\s*===\s*['"]not_running['"]/);
    assert.match(app, /pool\s*:/, 'pool sync must include the current backend pool contract');
    assert.match(app, /indices\s*:/, 'index sync must include the current backend indices contract');
    assert.match(app, /all\s*:/, 'combined P0-P2 sync must include the current backend all contract');
    for (const id of [
      'datasyncTaskDateFrom',
      'datasyncTaskDateTo',
      'datasyncTaskTypeFilter',
      'datasyncTaskStatusFilter',
      'datasyncTaskKeywordFilter',
      'datasyncTaskStats',
    ]) {
      assert.ok(html.includes(`id="${id}"`), `missing task filter/stat #${id}`);
    }
    for (const heading of ['开始时间', '更新任务', '范围 / 触发方式', '结果 (成功 / 失败)', '耗时', '状态', '操作']) {
      assert.ok(html.includes(`<th>${heading}</th>`), `missing task table heading ${heading}`);
    }
    const taskPanel = html.slice(html.indexOf('id="datasync-panel-tasks"'), html.indexOf('id="datasync-panel-settings"'));
    for (const id of ['datasyncTaskStatDegraded', 'datasyncTaskStatFailed', 'btnQueryDatasyncTasks', 'btnResetDatasyncTasks', 'btnLoadMoreDatasyncTasks']) {
      assert.ok(taskPanel.includes(`id="${id}"`), `missing reference control #${id}`);
    }
    for (const old of ['任务名称', '同步范围', '返回运行控制', '选择一条任务记录查看参数']) {
      assert.strictEqual(taskPanel.includes(old), false, `old task UI remains: ${old}`);
    }
    assert.ok(html.includes('id="btnRefreshDatasyncTasks"'), 'refresh records action is required');
    assert.ok(html.includes('id="btnExportDatasyncTasks"'), 'export records action is required');
    assert.match(app, /function exportDatasyncTasks\(/, 'export must use actual loaded task rows');
    assert.match(app, /recordVisibleCount:\s*8/, 'records start with eight visible rows');
    assert.match(app, /buildDatasyncRetryParams\(source\)/, 'retry must reuse failed-symbol guard');
  });

  await test('matrix 4: run page matches the approved reference content boundary', () => {
    const runPanel = html.slice(
      html.indexOf('id="datasync-panel-run"'),
      html.indexOf('id="datasync-panel-tasks"'),
    );
    for (const id of [
      'datasyncStatusGrid',
      'datasyncDailyHealthBody',
      'datasyncRecentTaskStatus',
      'datasyncAutoTitle',
    ]) {
      assert.ok(runPanel.includes(`id="${id}"`), `missing retained target field #${id}`);
    }
    for (const id of [
      'countHoldings',
      'btnSyncTodaySnapshot',
      'datasyncP3Scope',
      'cfgSyncConcurrency',
      'btnAuditIntegrity',
      'btnPingAllFeeds',
      'daemonLogTerminal',
      'tdxDropzone',
      'toggleSyncDaemon',
    ]) {
      assert.strictEqual(runPanel.includes(`id="${id}"`), false, `legacy field remains #${id}`);
    }
    for (const label of [
      '分级标的池增量同步',
      '多线程下载并发度',
      '数据连续性体检与智能自愈',
      '行情源诊断与链路探测',
      '查看服务内巡检与 CLI 守护日志',
      '通达信文件导入',
    ]) {
      assert.strictEqual(runPanel.includes(label), false, `legacy content remains: ${label}`);
    }
    assert.ok(!runPanel.includes('id="btnDatasyncAdvanced"'), 'misleading advanced-update link must be removed');
    assert.doesNotMatch(app, /btnDatasyncHeroRepair[\s\S]{0,180}btnRepairGaps['"]\)\?\.click\(\)/);
  });

  await test('matrix 4b: effective settings channel is real and drives the UI', async () => {
    assert.match(apiSource, /getDataSyncSettings\(\)[^{]*\{[^}]*\/api\/data-sync\/settings/, 'settings must load from the real console endpoint');
    assert.match(apiSource, /putDataSyncSettings/, 'PUT settings channel must exist for whitelisted saving');
    assert.match(app, /async function loadDatasyncSettings/, 'UI must read server-effective settings');
    assert.match(app, /capsule\.textContent = `自动增量：[\s\S]{0,300}p3\.time/, 'P3 auto-state capsule must show the scheduled time from settings');
    assert.match(app, /if \(nextTab === ['"]settings['"]\) loadDatasyncSettings\(\)/, 'settings tab must hydrate from the server');
    const settingsSource = fs.readFileSync(path.join(root, 'scripts/server/services/data_sync_settings.py'), 'utf8');
    assert.match(settingsSource, /ENV_OVERRIDE = ['"]A_STOCK_DATA_SYNC_SETTINGS_FILE['"]/, 'settings path must be overridable for test isolation');
    assert.match(settingsSource, /LOCAL_DIR \/ ['"]settings['"]/, 'settings must resolve under workspace LOCAL_DIR');
    assert.match(settingsSource, /os\.chmod\(tmp, 0o600\)|chmod\(path, 0o600\)/, 'persisted settings must be owner-only readable');
  });

  await test('matrix 5: data sync controller contains no fabricated success path', () => {
    const start = app.indexOf('DATA SYNC & MARKET HUB INTERACTIVE CONTROLLER');
    assert.ok(start >= 0, 'data sync controller section missing');
    const controller = app.slice(start);
    assert.strictEqual(controller.includes('Math.random'), false, 'random feed latency is forbidden');
    assert.strictEqual(/setTimeout\s*\(/.test(controller), false, 'delayed fake success is forbidden');
    for (const fakeText of [
      '链路全部就绪',
      '全量收盘价与筹码分布切片已固化落盘',
      '核心标的全部合规',
      '靶向自愈回补完成',
    ]) {
      assert.strictEqual(controller.includes(fakeText), false, `fabricated text remains: ${fakeText}`);
    }
    assert.strictEqual(html.includes('id="pingL1">● 运行中 (68ms)'), false);
    assert.strictEqual(html.includes('id="kpiHealthScore">98.5%'), false);
    assert.match(controller, /btnDatasyncHeroRepair[\s\S]{0,420}check:\s*true/, 'hero repair must request a real audit task directly');
    assert.match(controller, /btnDatasyncHeroRepair[\s\S]{0,420}repair:\s*true/, 'hero repair must request a real repair task directly');
    assert.match(
      apiSource,
      /pingMarketFeeds\(\)\s*\{[^}]*\/api\/market_data\/ping/,
      'feed probe must hit the real ping endpoint',
    );
    // 跨层防回归：ping 端点不得再把探测失败的源回落成历史伪造常量 68/124/150
    const pingSource = fs.readFileSync(path.join(root, 'scripts/server/api/market_data.py'), 'utf8');
    for (const fake of ['else 68', 'else 124', 'else 150']) {
      assert.strictEqual(pingSource.includes(fake), false, `ping endpoint must not fabricate latency: ${fake}`);
    }
    assert.match(app, /tabId\s*!==\s*['"]datasync['"][\s\S]{0,240}stopDatasyncPolling\s*\(/);
  });

  await test('matrix 6: daily health and settings controls use real endpoints', async () => {
    for (const label of ['数据更新', '更新记录', '同步配置']) {
      assert.ok(html.includes(`>${label}</button>`), `missing user-facing tab ${label}`);
    }
    for (const id of [
      'datasyncTargetDate', 'datasyncRegisteredCount', 'datasyncPendingCount',
      'datasyncAuditGapCount', 'datasyncDailyHealthBody', 'datasyncLastAuditTime',
      'datasyncRecentTaskStatus', 'datasyncRecentTaskResult', 'datasyncRecentTaskTime',
      'datasyncSettingsStatus', 'datasyncSettingAutoUpdate', 'datasyncSettingRunTime',
      'datasyncSettingConcurrency',
      'datasyncSettingImportType',
      'btnSaveDatasyncSettingsTop', 'btnResetDatasyncSettingsTop',
    ]) {
      assert.ok(html.includes(`id="${id}"`), `missing real console field #${id}`);
    }
    for (const page of ['common', 'performance', 'local', 'import']) {
      assert.ok(html.includes(`data-setting-page="${page}"`), `missing settings navigation ${page}`);
      assert.ok(html.includes(`data-setting-content="${page}"`), `missing settings content ${page}`);
    }
    for (const page of ['history', 'quality']) {
      assert.ok(!html.includes(`data-setting-page="${page}"`), `unsupported settings navigation remains: ${page}`);
    }
    assert.ok(!html.includes('id="datasyncSettingBaseMode"'), 'obsolete settings layout must be removed');
    assert.doesNotMatch(html, /id="datasyncSettingsPending"[^>]*>设置接口将在实施矩阵/);
    assert.match(app, /api\.getDataSyncOverview\s*\(/);
    assert.match(app, /api\.putDataSyncSettings\s*\(/);
    assert.match(app, /function\s+renderDatasyncOverview\s*\(/);
    assert.match(app, /function\s+renderDatasyncRecentTask\s*\(/);
    assert.match(app, /function\s+collectDatasyncSettings\s*\(/);
    assert.match(app, /DatasyncState\.repairCodes/);
    assert.match(app, /codes:\s*\[\.\.\.DatasyncState\.repairCodes\][\s\S]{0,80}repair:\s*true/);
    const calls = [];
    const api = loadAPI(async (url, options = {}) => {
      calls.push({ url, options });
      return jsonResponse({ status: 'success', settings: {} });
    });
    await api.getDataSyncOverview();
    await api.putDataSyncSettings({ daemon: { enabled: false } });
    await api.resetDataSyncSettings();
    assert.deepStrictEqual(calls.map(({ options }) => options.method || 'GET'), ['GET', 'PUT', 'POST']);
    assert.ok(calls[0].url.endsWith('/api/data-sync/overview'));
    assert.ok(calls[2].url.endsWith('/api/data-sync/settings/reset'));
  });

  await test('matrix 7: partial failures retry only the failed symbols', () => {
    const start = app.indexOf('function buildDatasyncRetryParams(');
    const end = app.indexOf('async function retryDatasyncTask(', start);
    assert.ok(start >= 0 && end > start, 'retry parameter builder must be a pure function');
    const sandbox = {};
    vm.createContext(sandbox);
    vm.runInContext(`${app.slice(start, end)}\nthis.build = buildDatasyncRetryParams;`, sandbox);
    const partial = {
      task_id: 'original-1', status: 'completed',
      params: { tier: 'P3', scope: 'full_market', mode: 'incremental', trigger: 'scheduled' },
      result: { failed_count: 2, failed_symbols: ['sh600519', 'sz000001'] },
    };
    const retry = sandbox.build(partial);
    assert.deepStrictEqual(Array.from(retry.codes), ['sh600519', 'sz000001']);
    assert.strictEqual(retry.scope, 'selected');
    assert.strictEqual(retry.retry_of, 'original-1');
    assert.strictEqual(retry.trigger, 'manual');
    assert.throws(() => sandbox.build({ ...partial, result: { failed_count: 2, failed_symbols: ['sh600519'] } }), /失败清单不完整/);
    const full = sandbox.build({ ...partial, status: 'failed', result: { error: 'upstream unavailable' } });
    assert.strictEqual(full.scope, 'full_market');
  });

  await test('settings columns scroll independently without the recommendation banner', () => {
    assert.doesNotMatch(html, /class="datasync-settings-recommendation"/);
    for (const removed of ['actionsDatasync', 'datasyncSettingSearch', 'datasync-settings-footer', 'btnSaveDatasyncSettings"', 'btnResetDatasyncSettings"']) {
      assert.ok(!html.includes(removed), `removed layout remains: ${removed}`);
    }
    assert.match(html, /id="btnSaveDatasyncSettingsTop"/);
    assert.match(html, /id="btnResetDatasyncSettingsTop"/);
    const layout = css.match(/body\.datasync-no-copilot \.datasync-settings-layout\.active\s*\{([^}]*)\}/)?.[1] || '';
    assert.match(layout, /grid-template-rows:\s*minmax\(0,\s*1fr\)/);
    assert.match(layout, /overflow:\s*hidden/);
    for (const selector of ['body.datasync-no-copilot .datasync-settings-domains', '.datasync-settings-workspace']) {
      const rule = css.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\{([^}]*)\\}`))?.[1] || '';
      assert.match(rule, /min-height:\s*0/);
      assert.match(rule, /overflow-y:\s*auto/);
    }
    assert.match(app, /if \(workspace\) workspace\.scrollTop = 0/);
  });

  await test('record results expose real success and failure counts', () => {
    const start = app.indexOf('function datasyncTaskResult(');
    const end = app.indexOf('function renderDatasyncRecentTask(', start);
    assert.ok(start >= 0 && end > start);
    const sandbox = {};
    vm.createContext(sandbox);
    vm.runInContext(`${app.slice(start, end)}\nthis.result = datasyncTaskResult; this.dataType = datasyncTaskDataType;`, sandbox);
    assert.deepStrictEqual(JSON.parse(JSON.stringify(sandbox.result({ result: { success_count: 5420, failed_count: 12 } }))), { succeeded: 5420, failed: 12 });
    assert.deepStrictEqual(JSON.parse(JSON.stringify(sandbox.result({ result: {} }))), { succeeded: null, failed: null });
    assert.strictEqual(sandbox.dataType({ params: { mode: 'audit' } }), 'other');
    assert.strictEqual(sandbox.dataType({ params: { check: true } }), 'other');
    assert.strictEqual(sandbox.dataType({ params: { repair: true } }), 'other');
    assert.strictEqual(sandbox.dataType({ params: { dataset: 'minute' } }), 'minute');
  });

  await test('matrix 8: coverage table shows only the connected daily dataset', () => {
    const start = app.indexOf('function renderDatasyncOverview(');
    const end = app.indexOf('async function loadDatasyncOverview(', start);
    assert.ok(start >= 0 && end > start);
    const elements = new Map();
    const document = {
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', className: '' });
        return elements.get(id);
      },
      querySelector() { return { disabled: false }; },
    };
    const sandbox = { document, escapeDatasyncHtml: String, datasyncDateTime: String };
    vm.createContext(sandbox);
    vm.runInContext(`${app.slice(start, end)}\nthis.render = renderDatasyncOverview;`, sandbox);
    sandbox.render({ daily_health: {
      target_date: '2026-09-30', target_note: '今日未定盘',
      registered: { total: 6, covered: 4, without_data: 2, pending: 2, state: 'pending', watermark_min: '2026-09-29', watermark_max: '2026-09-30' },
      tiers: { P0: { total: 1, state: 'fresh' }, P1: { total: 2, state: 'pending' }, P2: { total: 5, state: 'pending', watermark_min: '2026-09-29' } },
    }, daemon: { enabled: true }, last_audit: null });
    const body = elements.get('datasyncDailyHealthBody').innerHTML;
    assert.strictEqual((body.match(/<tr>/g) || []).length, 1);
    assert.ok(body.includes('日线行情'));
    assert.ok(!body.includes('分钟 K 线'));
    assert.strictEqual(elements.get('datasyncPendingCount').textContent, '2');
    assert.strictEqual(elements.get('datasyncAuditGapCount').textContent, '—');
    sandbox.render({ daily_health: {
      target_date: '2026-09-30', target_note: '今日未定盘',
      registered: { total: 6, covered: 4, without_data: 2, pending: 2, state: 'pending', watermark_min: '2026-09-29', watermark_max: '2026-09-30' },
      tiers: {},
    }, daemon: { enabled: true }, last_audit: null, dataset_coverage: [
      { key: 'base_calendar', name: '基础资料与交易日历', connected: true, scope: '2024-01-01 ～ 2027-12-31 规则日历', as_of: null, batch: '2024–2027 法定休市 66 天已内置', completeness: { state: 'complete', missing: 0, label: '齐全' }, state: 'fresh' },
      { key: 'daily_kline', name: '日线行情', connected: true, scope: '已登记范围 6 只', as_of: '2026-09-30', batch: null, completeness: { state: 'undetected', missing: null, label: '未检测' }, state: 'pending' },
      { key: 'minute_kline', name: '分钟K线', connected: false, scope: '未接入（规划：沪深北全市场 · 1/5/15/30/60 分钟）', as_of: null, batch: null, completeness: { state: 'undetected', missing: null, label: '未检测' }, state: 'unavailable' },
    ] });
    const coveredBody = elements.get('datasyncDailyHealthBody').innerHTML;
    assert.strictEqual((coveredBody.match(/<tr>/g) || []).length, 3);
    assert.ok(coveredBody.includes('分钟K线'));
    assert.ok(coveredBody.includes('未接入'));
    assert.ok(coveredBody.includes('is-good'));
    assert.doesNotMatch(css, /body\.datasync-no-copilot \.app-sidebar\s*\{[\s\S]*?background:\s*#1b2935/,
      '数据同步内容不得替换原系统左侧菜单的配色');
    assert.doesNotMatch(css, /body\.datasync-no-copilot \.app-header\s*,/,
      '数据同步内容不得隐藏原系统顶部框架');
    assert.doesNotMatch(css, /body\.datasync-no-copilot \.sidebar-sessions-section/,
      '数据同步内容不得隐藏原系统会话菜单');
    assert.doesNotMatch(html, /class="datasync-sidebar-brand"/,
      '不得为数据同步页添加替代性的左侧品牌区');
    sandbox.render(null);
    assert.strictEqual(elements.get('datasyncSyncLead').textContent, '状态暂不可用');
    assert.ok(!html.includes('id="datasyncWebRuntime"'));
  });

  await test('one click submits a batch parent instead of one long market task', () => {
    const action = app.slice(app.indexOf('function triggerManualSync()'), app.indexOf('function triggerManualSync()') + 400);
    assert.match(action, /data_sync_batch/);
    assert.doesNotMatch(action, /full_market|selected_pools/);
    assert.match(app, /task_type:\s*taskType/);
    assert.match(app, /parent_task_id/, 'child records should appear under a parent task');
    assert.ok(html.includes('沪深全市场与核心指数日线'));
  });

  await test('batch parent groups child records and reports partial failure', () => {
    const start = app.indexOf('function datasyncEffectiveStatus(');
    const end = app.indexOf('function datasyncTaskId(', start);
    const sandbox = {};
    vm.createContext(sandbox);
    vm.runInContext(`${app.slice(start, end)}\nthis.status = datasyncEffectiveStatus; this.normalize = normalizeDatasyncTasks;`, sandbox);
    const parent = { task_type: 'data_sync_batch', status: 'completed', result: { status: 'degraded', failed_tasks: 1, failed_count: 0 } };
    assert.strictEqual(sandbox.status(parent), 'degraded');
    assert.strictEqual(sandbox.normalize([parent]).length, 1);
    const records = app.slice(app.indexOf('function renderDatasyncTaskDetail('), app.indexOf('function exportDatasyncTasks('));
    assert.match(records, /result\.children/);
    assert.match(records, /parent_task_id/);
    assert.match(records, /分项任务/);
  });

  await test('settings save excludes removed target-only controls', () => {
    const start = app.indexOf('function datasyncSettingValue(');
    const end = app.indexOf('function datasyncImportError(', start);
    const sources = app.slice(start, end);
    const fields = {
      datasyncSettingRunTime: { value: '16:30' },
      datasyncSettingFrequency: { value: 'trading_day' },
      datasyncSettingAutoUpdate: { checked: true },
      datasyncSettingConcurrency: { value: '4' },
      datasyncSettingBatchSize: { value: '600' },
      datasyncSettingTimeout: { value: '300' },
      datasyncSettingImportType: { value: 'daily' },
      datasyncSettingImportValidate: { checked: true },
    };
    const document = {
      getElementById(id) { return fields[id] || null; },
      querySelector(selector) { return selector.includes('datasyncImportMode') ? { value: 'missing' } : null; },
    };
    const sandbox = { document };
    vm.createContext(sandbox);
    vm.runInContext(`${sources}\nthis.collect = collectDatasyncSettings;`, sandbox);
    const patch = JSON.parse(JSON.stringify(sandbox.collect()));
    assert.deepStrictEqual(Object.keys(patch).sort(), ['base', 'daemon', 'p3', 'workspace']);
    assert.deepStrictEqual(Object.keys(patch.workspace).sort(), ['common', 'import_rules']);
    assert.strictEqual(patch.p3.batch_size, 600);
  });

  const failures = results.filter((result) => !result.ok);
  if (failures.length) {
    console.error(`\n${failures.length}/${results.length} data sync console matrix tests failed.`);
    process.exitCode = 1;
    return;
  }
  console.log(`\n${results.length}/${results.length} data sync console matrix tests passed.`);
})();
