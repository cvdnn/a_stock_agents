const assert = require('assert');
const fs = require('fs');

const source = fs.readFileSync('web/js/app.js', 'utf8');
const helperStart = source.indexOf('function isRoleOptionCompatible(');
const helperEnd = source.indexOf('function renderModelRolesDropdowns()', helperStart);

assert.ok(helperStart >= 0, 'app.js must define isRoleOptionCompatible');
assert.ok(helperEnd > helperStart, 'role option helper must precede role dropdown rendering');

const chooseDefaultRoleOption = new Function(
  `${source.slice(helperStart, helperEnd)}; return chooseDefaultRoleOption;`
)();

const options = [
  { value: '', label: '-- 请选择模型 (未指定) --' },
  { value: 'general|provider-1', label: 'General | Provider', capabilities: ['chat'] },
  { value: 'tools|provider-1', label: 'Tools | Provider', capabilities: ['chat', 'tools'] },
  { value: 'tools-alt|provider-1', label: 'Tools Alt | Provider', capabilities: ['chat', 'tools'] },
  { value: 'flash|provider-1', label: 'Flash | Provider', capabilities: ['chat', 'fast'] },
  { value: 'reasoner|provider-1', label: 'Reasoner | Provider', capabilities: ['chat', 'reasoning'] },
  { value: 'vision|provider-1', label: 'Vision | Provider', capabilities: ['chat', 'vision'] },
];

assert.strictEqual(chooseDefaultRoleOption('chat', options).value, 'tools|provider-1');
assert.strictEqual(chooseDefaultRoleOption('quant', options).value, 'tools|provider-1');
assert.strictEqual(chooseDefaultRoleOption('summary', options).value, 'flash|provider-1');
assert.strictEqual(chooseDefaultRoleOption('debate', options).value, 'reasoner|provider-1');
assert.strictEqual(chooseDefaultRoleOption('vision', options).value, 'vision|provider-1');
assert.strictEqual(chooseDefaultRoleOption('chat', options.slice(0, 1)), null);
assert.strictEqual(chooseDefaultRoleOption('chat', options.slice(0, 2)), null);
assert.strictEqual(chooseDefaultRoleOption('quant', options.slice(0, 2)), null);

const renderStart = source.indexOf('function renderModelRolesDropdowns()');
const renderEnd = source.indexOf('function handleRoleChange(', renderStart);
const renderSource = source.slice(renderStart, renderEnd);
assert.ok(renderSource.includes('handleRoleChange(role, select.value)'));
assert.ok(renderSource.includes("capabilities: m.capabilities || ['chat']"));

const saveStart = source.indexOf('async function saveSettings()', renderEnd);
const appState = {
  providers: [{
    provider_id: 'provider-1',
    name: 'Provider',
    enabled: true,
    models: options.slice(1).map(option => ({
      id: option.value.split('|')[0],
      name: option.label.split(' | ')[0],
      capabilities: option.capabilities,
      selected: true,
    })),
  }],
  modelRoles: {},
};
const selects = Object.fromEntries(
  ['chat', 'summary', 'quant', 'debate', 'vision'].map(role => [role, { value: '', innerHTML: '' }])
);
const fakeDocument = {
  getElementById(id) {
    return selects[id.replace('roleSelect_', '')] || null;
  },
};
const runtimeFactory = new Function(
  'AppState',
  'document',
  `${source.slice(helperStart, saveStart)}; return { renderModelRolesDropdowns };`
);
const runtime = runtimeFactory(appState, fakeDocument);

runtime.renderModelRolesDropdowns();
assert.deepStrictEqual(appState.modelRoles.chat, { model_id: 'tools', provider_id: 'provider-1' });
assert.deepStrictEqual(appState.modelRoles.quant, { model_id: 'tools', provider_id: 'provider-1' });
assert.deepStrictEqual(appState.modelRoles.summary, { model_id: 'flash', provider_id: 'provider-1' });
assert.deepStrictEqual(appState.modelRoles.debate, { model_id: 'reasoner', provider_id: 'provider-1' });
assert.deepStrictEqual(appState.modelRoles.vision, { model_id: 'vision', provider_id: 'provider-1' });

appState.modelRoles.chat = { model_id: 'tools-alt', provider_id: 'provider-1' };
runtime.renderModelRolesDropdowns();
assert.deepStrictEqual(appState.modelRoles.chat, { model_id: 'tools-alt', provider_id: 'provider-1' });
assert.strictEqual(selects.chat.value, 'tools-alt|provider-1');

appState.modelRoles.chat = { model_id: 'general', provider_id: 'provider-1' };
runtime.renderModelRolesDropdowns();
assert.deepStrictEqual(appState.modelRoles.chat, { model_id: 'tools', provider_id: 'provider-1' });
assert.strictEqual(selects.chat.value, 'tools|provider-1');

const noToolsState = {
  providers: [{
    provider_id: 'provider-1',
    name: 'Provider',
    enabled: true,
    models: [{ id: 'general', name: 'General', capabilities: ['chat'], selected: true }],
  }],
  modelRoles: {
    chat: { model_id: 'general', provider_id: 'provider-1' },
    quant: { model_id: 'general', provider_id: 'provider-1' },
  },
};
const noToolsSelects = Object.fromEntries(
  ['chat', 'summary', 'quant', 'debate', 'vision'].map(role => [role, { value: '', innerHTML: '' }])
);
const noToolsRuntime = runtimeFactory(noToolsState, {
  getElementById(id) {
    return noToolsSelects[id.replace('roleSelect_', '')] || null;
  },
});

noToolsRuntime.renderModelRolesDropdowns();
assert.deepStrictEqual(noToolsState.modelRoles.chat, { provider_id: '', model_id: '' });
assert.deepStrictEqual(noToolsState.modelRoles.quant, { provider_id: '', model_id: '' });
assert.strictEqual(noToolsSelects.chat.value, '');
assert.strictEqual(noToolsSelects.quant.value, '');

console.log('model role defaults: PASS');
