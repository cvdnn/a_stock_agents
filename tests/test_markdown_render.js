// tests/test_markdown_render.js
const fs = require('fs');
const path = require('path');
const assert = require('assert');

console.log('=== [AIChatUI Markdown 渲染组件自动化回归测试套件] ===\n');

// 1. 验证本地依赖文件就地存在
const markedPath = path.join(__dirname, '../web/js/libs/marked.min.js');
const hljsPath = path.join(__dirname, '../web/js/libs/highlight.min.js');
const purifyPath = path.join(__dirname, '../web/js/libs/purify.min.js');
const cssPath = path.join(__dirname, '../web/css/highlight-github.min.css');

assert(fs.existsSync(markedPath), 'marked.min.js 必须就地存在');
assert(fs.existsSync(hljsPath), 'highlight.min.js 必须就地存在');
assert(fs.existsSync(purifyPath), 'purify.min.js 必须就地存在');
assert(fs.existsSync(cssPath), 'highlight-github.min.css 必须就地存在');
console.log('✔ 测试 1 通过: 4 项本地化静态依赖库文件完整存在，零外部网络强依赖');

// 2. 模拟浏览器环境加载依赖与 chat_presentation.js
const markedCode = fs.readFileSync(markedPath, 'utf8');
const hljsCode = fs.readFileSync(hljsPath, 'utf8');
const purifyCode = fs.readFileSync(purifyPath, 'utf8');
const chatPresCode = fs.readFileSync(path.join(__dirname, '../web/js/chat_presentation.js'), 'utf8');

const mockWindow = {};
const mockGlobal = {
  window: mockWindow,
  navigator: { clipboard: { writeText: () => Promise.resolve() } },
  document: {
    createElement: (tag) => ({ style: {}, appendChild: () => {}, select: () => {}, focus: () => {} }),
    body: { appendChild: () => {}, removeChild: () => {} }
  }
};

// 执行 marked, hljs, purify 到 mockWindow
const vm = require('vm');
const ctx = vm.createContext(mockGlobal);
vm.runInContext(markedCode, ctx);
vm.runInContext(hljsCode, ctx);
vm.runInContext(purifyCode, ctx);

// 执行 chat_presentation.js
vm.runInContext(chatPresCode, ctx);

const ChatPresentation = mockGlobal.window.ChatPresentation || mockGlobal.ChatPresentation;
assert(ChatPresentation, 'ChatPresentation 必须成功挂载在 window 上');
assert(typeof ChatPresentation.renderMarkdown === 'function', 'renderMarkdown 必须为函数');
assert(typeof ChatPresentation.copyCodeBlock === 'function', 'copyCodeBlock 必须为函数');
console.log('✔ 测试 2 通过: ChatPresentation 引擎成功初始化并挂载');

// 3. 测试表格解析与响应式外框包裹
const tableMd = `
| 股票代码 | 股票名称 | 现价 | 保本卖出价 | 建议动作 |
| :--- | :--- | :---: | :---: | :--- |
| 600519 | 贵州茅台 | 1480.00 | 1483.71 | 震荡观望 |
| 000001 | 平安银行 | 11.20 | 11.23 | 保本持有 |
`;
const tableHtml = ChatPresentation.renderMarkdown(tableMd);
assert(tableHtml.includes('<div class="table-responsive">'), '表格必须被 table-responsive 包裹');
assert(tableHtml.includes('<table>'), '必须包含 table 标签');
assert(tableHtml.includes('贵州茅台'), '表格内容必须完整保留');
assert(tableHtml.includes('1483.71'), '表格金额必须完整保留');
console.log('✔ 测试 3 通过: 金融多列表格正确渲染并包裹响应式外框容器');

// 4. 测试多语言代码块、高亮与一键复制代码工具栏
const codeMd = `
\`\`\`python
# A-Stock 保本价进位精算
import math
def calc_breakeven(cost, shares):
    tax = 0.0005
    commission = max(5.0, cost * shares * 0.00025)
    return math.ceil((cost * shares + commission) / (shares * (1 - tax)) * 100) / 100
\`\`\`
`;
const codeHtml = ChatPresentation.renderMarkdown(codeMd);
assert(codeHtml.includes('code-block-wrapper'), '代码块必须具有 code-block-wrapper 包装器');
assert(codeHtml.includes('code-block-header'), '代码块必须具有顶部工具栏');
assert(codeHtml.includes('PYTHON'), '语言标签必须识别为 PYTHON');
assert(codeHtml.includes('code-copy-btn'), '必须具备一键复制代码按钮');
assert(codeHtml.includes('hljs'), '必须经过 highlight.js 染色注入 hljs 类');
assert(codeHtml.includes('hljs-keyword'), 'Python 关键字必须染色');
console.log('✔ 测试 4 通过: Python 代码块高亮与复制代码工具栏渲染完备');

// 5. 测试 GFM Callouts / Alerts 警示卡片渲染
const alertMd = `
> [!IMPORTANT]
> 严格遵守实战交易三原则：保本价必须向上进位，绝不允许四舍五入！

> [!WARNING]
> 触发 T2 绝杀线（-8%），无条件止损出局！
`;
const alertHtml = ChatPresentation.renderMarkdown(alertMd);
assert(alertHtml.includes('gfm-alert gfm-alert-important'), '必须正确渲染 [!IMPORTANT] 提示框');
assert(alertHtml.includes('重要提示'), '必须呈现“重要提示”标题');
assert(alertHtml.includes('gfm-alert gfm-alert-warning'), '必须正确渲染 [!WARNING] 警示框');
assert(alertHtml.includes('风控警告'), '必须呈现“风控警告”标题');
console.log('✔ 测试 5 通过: GFM Callout 警示框与金融风控提示卡片解析正确');

// 6. 测试 GFM 任务清单与多级列表
const taskMd = `
- [x] 1. 完成主力资金与换手沉淀排查
- [x] 2. 向上进位精算保本卖出价
- [ ] 3. 盘中触及 T1 减仓线（-5%）执行防守
`;
const taskHtml = ChatPresentation.renderMarkdown(taskMd);
assert(taskHtml.includes('type="checkbox"'), '任务清单必须渲染为原生 checkbox');
console.log('✔ 测试 6 通过: GFM 任务列表复选框渲染正常');

// 7. 测试 XSS 注入消毒与安全净化
const xssMd = `恶意注入：<script>alert("hacked")</script><img src="x" onerror="alert(1)">[点击恶意链接](javascript:alert(1))`;
const safeHtml = ChatPresentation.renderMarkdown(xssMd);
assert(!safeHtml.includes('<script>'), '不得包含未经消毒的 script 标签');
assert(!safeHtml.includes('onerror='), '不得包含内联 onerror 事件');
assert(!safeHtml.includes('javascript:'), '不得执行 javascript 伪协议');
console.log('✔ 测试 7 通过: DOMPurify 严密过滤恶意脚本与 XSS 注入');

// 8. 测试 <think> 思考链清洗（含流式未闭合片段）
const thinkMd1 = `<think>正在规划推演逻辑...</think># 研报核心结论\n买入评级。`;
const thinkHtml1 = ChatPresentation.renderMarkdown(thinkMd1);
assert(!thinkHtml1.includes('正在规划推演逻辑'), '闭合的 <think> 必须彻底剔除');
assert(thinkHtml1.includes('研报核心结论'), '正常正文必须保留');

const thinkMd2 = `<think>流式生成中尚未闭合的内容...`;
const thinkHtml2 = ChatPresentation.renderMarkdown(thinkMd2);
assert(!thinkHtml2.includes('尚未闭合的内容'), '未闭合的 <think> 也必须在流式展示中优雅屏蔽');
console.log('✔ 测试 8 通过: 模型思考过程 (<think>) 无论闭合还是流式截断均被完美剥离');

// 9. 测试流式输出下未闭合代码块与表格的容错性
const streamingIncompleteMd = `### 量化策略代码片段\n\`\`\`python\nprint("streaming data")`;
const streamingHtml = ChatPresentation.renderMarkdown(streamingIncompleteMd);
assert(streamingHtml.includes('code-block-wrapper'), '未闭合的代码块在流式状态下必须优雅补全');
assert(streamingHtml.includes('streaming data'), '未闭合的内容不得丢失');
console.log('✔ 测试 9 通过: AI 流式未闭合代码块容错性测试通过');

console.log('\n🎉 ALL 9 TESTS PASSED! AIChatUI Markdown 渲染引擎升级验收全部合格！\n');
