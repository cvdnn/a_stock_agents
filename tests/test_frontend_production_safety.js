const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync('web/js/api.js', 'utf8');

function responseFromSSE(text, ok = true, status = 200) {
  let delivered = false;
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Bad Request',
    async json() { return { detail: 'request failed' }; },
    body: {
      getReader() {
        return {
          async read() {
            if (delivered) return { done: true };
            delivered = true;
            return { done: false, value: new TextEncoder().encode(text) };
          }
        };
      }
    }
  };
}

function loadAPI(fetchImpl) {
  const sandbox = { window: {}, fetch: fetchImpl, TextDecoder, console };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return sandbox.window.AStockAPI;
}

async function runStream(api, payload) {
  const counts = { done: 0, error: 0 };
  await api.streamChatCompletions('hello', 'session-1', undefined, {
    onDone() { counts.done += 1; },
    onError() { counts.error += 1; },
  });
  return counts;
}

(async () => {
  const rejected = loadAPI(async () => { throw new Error('offline'); });
  await assert.rejects(() => rejected.getMarketIndices(), /offline/);

  const serverError = loadAPI(async () => responseFromSSE(
    'event: error\ndata: {"code":"LLM_NOT_CONFIGURED","error":"not ready"}\n\n'
  ));
  assert.deepStrictEqual(await runStream(serverError), { done: 0, error: 1 });

  const malformed = loadAPI(async () => responseFromSSE('event: done\ndata: not-json\n\n'));
  assert.deepStrictEqual(await runStream(malformed), { done: 0, error: 1 });

  const success = loadAPI(async () => responseFromSSE(
    'event: content_delta\ndata: {"text":"ok"}\n\nevent: done\ndata: {"total_tokens":2}\n\n'
  ));
  assert.deepStrictEqual(await runStream(success), { done: 1, error: 0 });

  const httpFailure = loadAPI(async () => responseFromSSE('', false, 503));
  assert.deepStrictEqual(await runStream(httpFailure), { done: 0, error: 1 });

  const bodies = [];
  const capture = loadAPI(async (_url, options) => {
    bodies.push(JSON.parse(options.body));
    if (_url.includes('/stream')) {
      return responseFromSSE('event: done\ndata: {"total_tokens":0}\n\n');
    }
    return { ok: true, status: 200, statusText: 'OK', async json() { return { session_id: 's1' }; } };
  });
  await capture.createSession('title');
  await capture.streamChatCompletions('hello', 's1', undefined, {});
  assert.strictEqual(Object.prototype.hasOwnProperty.call(bodies[0], 'model'), false);
  assert.strictEqual(Object.prototype.hasOwnProperty.call(bodies[1], 'model'), false);
  assert.strictEqual(source.includes('Fallback Mock'), false);
  assert.strictEqual(source.includes("model = 'mock'"), false);

  const components = fs.readFileSync('web/js/components/astock.js', 'utf8');
  for (const fabricated of ['3426.56', '10892.14', '1.28万亿元', '78分 贪婪', 'props.cost || 320.0']) {
    assert.strictEqual(components.includes(fabricated), false);
  }
  assert.ok(components.includes('市场指数数据不可用'));
  assert.ok(components.includes('缺少有效持仓成本或股数'));

  console.log('frontend production safety: PASS');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
