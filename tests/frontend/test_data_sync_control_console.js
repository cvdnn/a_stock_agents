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
    assert.match(app, /task_type\s*:\s*['"]data_sync['"]/);
    assert.match(app, /task_type\s*===\s*['"]sync['"]|\[['"]data_sync['"],\s*['"]sync['"]\]/);
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
    for (const heading of ['开始时间', '任务名称', '同步范围', '模式', '结果', '状态', '耗时', '操作']) {
      assert.ok(html.includes(`<th>${heading}</th>`), `missing task table heading ${heading}`);
    }
  });

  await test('matrix 4: P3 controls expose real scope, mode, progress and automatic state', () => {
    for (const id of [
      'datasyncP3Scope',
      'datasyncP3Mode',
      'datasyncP3Codes',
      'btnDatasyncP3Start',
      'datasyncP3Progress',
      'datasyncP3Processed',
      'datasyncP3Succeeded',
      'datasyncP3Failed',
      'datasyncP3Batch',
      'datasyncP3Remaining',
      'datasyncP3AutoState',
      'datasyncP3TaskId',
      'datasyncP3Total',
    ]) {
      assert.ok(html.includes(`id="${id}"`), `missing #${id}`);
    }
    assert.match(app, /scope\s*:\s*[^,\n]+/);
    assert.match(app, /mode\s*:\s*[^,\n]+/);
    assert.match(app, /mode\s*===\s*['"]full['"][\s\S]{0,500}confirm\s*\(/);
    assert.match(app, /getElementById\(['"]datasyncP3ProgressBar['"]\)/, 'progress width must target the inner bar');
    assert.match(app, /numeric\s*<=\s*1[\s\S]{0,160}numeric\s*\*\s*100/, '0-1 backend progress must be normalized to percent');
    assert.match(app, /scope\s*!==\s*['"]selected['"]/, 'unsupported P3 market scopes must fail closed until backend support lands');
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
    for (const id of ['btnSyncTodaySnapshot', 'btnPingAllFeeds', 'btnAuditIntegrity', 'btnRepairGaps']) {
      assert.match(html, new RegExp(`id="${id}"[^>]*disabled`), `${id} must be disabled until a truthful backend exists`);
    }
    assert.match(app, /tabId\s*!==\s*['"]datasync['"][\s\S]{0,240}stopDatasyncPolling\s*\(/);
  });

  const failures = results.filter((result) => !result.ok);
  if (failures.length) {
    console.error(`\n${failures.length}/${results.length} data sync console matrix tests failed.`);
    process.exitCode = 1;
    return;
  }
  console.log(`\n${results.length}/${results.length} data sync console matrix tests passed.`);
})();
