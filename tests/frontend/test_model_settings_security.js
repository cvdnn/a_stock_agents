const assert = require('assert');
const fs = require('fs');

const source = fs.readFileSync('web/js/app.js', 'utf8');

assert.strictEqual(/localStorage\.(getItem|setItem)\(['"]astock_llm_providers/.test(source), false);
assert.strictEqual(source.includes('loadProvidersFromLocalStorage'), false);
assert.strictEqual(source.includes('fallbackTypewriter'), false);
assert.strictEqual(source.includes("'mock',"), false);
assert.strictEqual(source.includes('body: JSON.stringify({ base_url, api_key'), false);
assert.ok(source.includes('body: JSON.stringify({ provider_id: AppState.activeProviderId'));
assert.ok(source.includes("localStorage.removeItem('astock_llm_providers')"));

console.log('model settings security: PASS');
