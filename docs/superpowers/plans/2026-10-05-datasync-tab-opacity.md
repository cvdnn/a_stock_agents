# 数据同步 Tab 穿透修复实施计划

**目标：** 保留【数据同步】Tab 栏吸顶行为，并以页面同色的不透明背景阻止滚动内容穿透。

## 任务 1：建立回归测试

**文件：** `tests/frontend/test_data_sync_control_console.js`

1. 在数据同步控制台样式契约中加入断言，要求 `body.datasync-no-copilot .datasync-tabs` 使用 `#f5f8fc` 背景。
2. 明确拒绝同一规则继续使用 `background: transparent`。
3. 单独运行该测试，确认它因现有透明背景而失败。

## 任务 2：实施最小修复

**文件：** `web/css/style.css`

1. 仅将数据同步页面后置规则中的 Tab 容器背景从 `transparent` 改为 `#f5f8fc`。
2. 不调整吸顶定位、层级、尺寸、间距或单个 Tab 的状态样式。

## 任务 3：验证

1. 重新运行数据同步前端测试，确认新增断言通过。
2. 运行相关前端测试集，确认无回归。
3. 检查最终差异，确保没有覆盖工作区中的无关改动。
