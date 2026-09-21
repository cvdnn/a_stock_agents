const assert = require('assert');
const fs = require('fs');

const source = fs.readFileSync('web/js/app.js', 'utf8');
const match = source.match(/function formatOptionalDecimal\s*\([^)]*\)\s*\{[\s\S]*?\n\}/);

assert.ok(match, 'app.js must define formatOptionalDecimal for nullable market values');

const formatOptionalDecimal = new Function(
  `${match[0]}; return formatOptionalDecimal;`
)();

assert.strictEqual(formatOptionalDecimal(null), '--');
assert.strictEqual(formatOptionalDecimal(undefined), '--');
assert.strictEqual(formatOptionalDecimal(Number.NaN), '--');
assert.strictEqual(formatOptionalDecimal(12.3), '12.30');

const renderStart = source.indexOf('renderItemsList() {');
const renderEnd = source.indexOf('\n  updateItemSelection() {', renderStart);
const renderSource = source.slice(renderStart, renderEnd);

assert.ok(renderSource.includes('formatOptionalDecimal(item.currentPrice)'));
assert.ok(renderSource.includes('formatOptionalDecimal(item.costPrice)'));
assert.ok(renderSource.includes('formatOptionalDecimal(item.changePct)'));

console.log('at operator nullable market values: PASS');
