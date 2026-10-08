import assert from 'node:assert/strict';
import test from 'node:test';
import { assessDemo, sampleTrace } from '../src/lib/demo.ts';

test('nominal and reset are deterministic, passing and explicitly synthetic', () => {
  const result = assessDemo('nominal');
  assert.equal(result.verdict, 'PASS');
  assert.equal(result.passing, 4);
  assert.equal(result.evidenceKind, 'synthetic');
  assert.deepEqual(result, assessDemo('nominal'));
});
for (const [failure, gate] of [['sensor', 'sensor'], ['scene', 'perception'], ['drift', 'tracking']]) {
  test(`${failure} changes the correct gate and holds`, () => {
    const result = assessDemo(failure);
    assert.equal(result.verdict, 'BLOCK');
    assert.equal(result.decision, 'HOLD');
    assert.equal(result.gates.find(item => item.id === gate).state, 'BLOCK');
    assert.equal(result.passing, 3);
  });
}
test('trace remains nominal before injection and does not introduce NaN', () => {
  assert.deepEqual(sampleTrace(20, 'drift'), sampleTrace(20, 'nominal'));
  for (const failure of ['nominal', 'sensor', 'scene', 'drift']) {
    assert.ok(assessDemo(failure).samples.every(sample => sample.observed.every(Number.isFinite)));
  }
});