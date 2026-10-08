const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(path.join(__dirname, '../../web/js/api.js'), 'utf8');

function baseUrl(hostname, port) {
  const context = vm.createContext({ window: { location: { hostname, port } } });
  vm.runInContext(source, context);
  return vm.runInContext('AStockAPI.baseUrl', context);
}

assert.strictEqual(baseUrl('127.0.0.1', '6300'), '');
assert.strictEqual(baseUrl('127.0.0.1', '6312'), '', 'isolated API service must remain same-origin');
assert.strictEqual(baseUrl('localhost', '6312'), '', 'localhost isolated service must remain same-origin');
assert.strictEqual(baseUrl('localhost', '5173'), 'http://127.0.0.1:6300');
assert.strictEqual(baseUrl('127.0.0.1', '3000'), 'http://127.0.0.1:6300');
assert.strictEqual(baseUrl('example.test', '5173'), '', 'non-local hosts must never be redirected to loopback');

console.log('test_api_base_url: ok');
