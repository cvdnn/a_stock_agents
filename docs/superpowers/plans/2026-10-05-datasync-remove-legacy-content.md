# Data Sync Legacy Content Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the “数据更新” tab match `docs/images/21_27_35.png` by removing every confirmed legacy control while preserving the new overview, task history, settings, and backend sync capabilities.

**Architecture:** Treat the reference screenshot as the run-tab view contract. Remove obsolete run-tab DOM, update the remaining actions so they call backend tasks directly instead of clicking deleted controls, and lock the boundary with a static frontend matrix test. Keep server APIs and the other two tab panels unchanged.

**Tech Stack:** Static HTML/CSS, browser JavaScript, Node.js assertion tests, Python/pytest server regression tests.

---

### Task 1: Lock the target run-tab contract with a failing test

**Files:**
- Modify: `tests/frontend/test_data_sync_control_console.js`

- [ ] **Step 1: Replace legacy-control assertions with presence/absence assertions**

Add a matrix case that requires the retained target IDs and rejects the removed IDs and labels:

```js
await test('matrix 4: run page matches the approved reference content boundary', () => {
  for (const id of [
    'datasyncStatusGrid', 'datasyncDailyHealthBody',
    'datasyncRecentTaskStatus', 'datasyncAutoTitle',
  ]) {
    assert.ok(html.includes(`id="${id}"`), `missing retained target field #${id}`);
  }
  for (const id of [
    'countHoldings', 'btnSyncTodaySnapshot', 'datasyncP3Scope',
    'cfgSyncConcurrency', 'btnAuditIntegrity', 'btnPingAllFeeds',
    'daemonLogTerminal', 'tdxDropzone', 'toggleSyncDaemon',
  ]) {
    assert.strictEqual(html.includes(`id="${id}"`), false, `legacy field remains #${id}`);
  }
  for (const label of [
    '分级标的池增量同步', 'P3 全市场同步', '多线程下载并发度',
    '数据连续性体检与智能自愈', '行情源诊断与链路探测',
    '查看服务内巡检与 CLI 守护日志', '通达信文件导入',
  ]) {
    assert.strictEqual(html.includes(label), false, `legacy content remains: ${label}`);
  }
});
```

Remove the prior matrix assertions that required P3 run controls and the four deleted legacy buttons.

- [ ] **Step 2: Run the frontend matrix and confirm the new test fails**

Run: `node tests/frontend/test_data_sync_control_console.js`

Expected: FAIL because `web/index.html` still contains the legacy IDs and labels.

- [ ] **Step 3: Commit the red test checkpoint**

```bash
git add tests/frontend/test_data_sync_control_console.js
git commit -m "test(datasync): define approved run-page content boundary"
```

### Task 2: Remove obsolete run-tab content and repair retained actions

**Files:**
- Modify: `web/index.html`
- Modify: `web/js/app.js`

- [ ] **Step 1: Delete the confirmed legacy DOM from the run panel**

Delete `.datasync-col-main` in full. Inside `.datasync-col-sidebar`, retain only `.datasync-recent-card` and `.daemon-card`; delete both diagnostics details blocks, the daemon log details block, the TDX import details block, and the hidden Web-daemon toggle. Preserve the closing tags for `#datasync-panel-run` and all markup for the tasks/settings panels.

- [ ] **Step 2: Make retained actions independent of deleted controls**

Use direct task creation/routing in `initDatasync()`:

```js
document.getElementById('datasyncDailyHealthBody')?.addEventListener('click', (event) => {
  const button = event.target.closest('[data-health-action]');
  if (!button) return;
  if (button.dataset.healthAction === 'sync-all') triggerManualSync();
  if (button.dataset.healthAction === 'sync-indices') {
    createDataSyncTask({ tier: 'P2', scope: 'indices', mode: 'incremental', indices: true }, button);
  }
});
document.getElementById('btnDatasyncHeroRepair')?.addEventListener('click', () => {
  const params = DatasyncState.repairCodes.length
    ? { codes: [...DatasyncState.repairCodes], repair: true, mode: 'repair' }
    : { all: true, indices: true, check: true };
  createDataSyncTask(params, document.getElementById('btnDatasyncHeroRepair'));
});
document.getElementById('btnDatasyncAdvanced')?.addEventListener('click', () => {
  switchDatasyncTab('settings');
});
```

Remove initialization blocks for P3 run controls, pool cards, concurrency slider, audit table controls, feed ping, today snapshot, daemon log stream, TDX picker, and the removed daemon toggle. Keep shared task polling, overview rendering, settings hydration, recent-task rendering, and automatic-update status refresh.

- [ ] **Step 3: Run the frontend matrix and confirm it passes**

Run: `node tests/frontend/test_data_sync_control_console.js`

Expected: all data sync console matrix tests pass.

- [ ] **Step 4: Commit the implementation**

```bash
git add web/index.html web/js/app.js tests/frontend/test_data_sync_control_console.js
git commit -m "refactor(datasync): remove superseded run-page controls"
```

### Task 3: Verify no visual or server contract regression

**Files:**
- Verify: `web/index.html`
- Verify: `web/js/app.js`
- Verify: `tests/frontend/test_data_sync_control_console.js`
- Verify: `tests/server/test_data_sync_settings.py`
- Verify: `tests/server/test_market_data_sync_api.py`

- [ ] **Step 1: Scan for every deleted content marker**

Run:

```powershell
rg -n "分级标的池增量同步|同步今日快照|P3 全市场同步|多线程下载并发度|数据连续性体检与智能自愈|行情源诊断与链路探测|查看服务内巡检与 CLI 守护日志|通达信文件导入" web/index.html
```

Expected: no matches in the run-page HTML. The P3 label may remain only in the retained settings panel, so validate any `P3 全市场同步` match is under `#datasync-panel-settings`.

- [ ] **Step 2: Run focused frontend regression tests**

Run: `node tests/frontend/test_data_sync_control_console.js`

Expected: exit code 0 with all matrix cases passing.

- [ ] **Step 3: Run focused server regression tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/server/test_data_sync_settings.py tests/server/test_market_data_sync_api.py -q`

Expected: exit code 0; all selected tests pass.

- [ ] **Step 4: Run diff hygiene checks**

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 5: Review the final diff against the approved design**

Confirm the run panel contains only the header, tabs, phase strip, status cards, coverage table, recent update card, and automatic update card; confirm the task/settings panels and server files are unchanged by this implementation.
