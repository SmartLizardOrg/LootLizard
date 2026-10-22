/** Worker transport tests use a Python bridge surrogate, not a mock CV claim.
 * The hosted browser probe separately exercises the actual Pyodide runtime.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

function harness() {
  const replies = [], calls = [], destroyed = [];
  const engine = {
    clear() {return {count: 0};},
    destroy() {destroyed.push('engine');},
    set_references(records) {calls.push({type: 'references', records: records.value}); return {count: records.value.length};},
    analyze_rgba(buffer, width, height, context, ticket, mapId) {
      calls.push({type: 'analyze', buffer: buffer.value, width, height, context, mapId});
      return {width, height, registration: null, position: null, zone: null, points: [], timings: {markerMs: 0, zoneMs: 0}};
    },
  };
  const constructor = Object.assign(() => engine, {destroy() {destroyed.push('constructor');}});
  const py = {globals: {get(name) {
    if (name === 'BrowserVisionEngine') return constructor;
    return {toJs() {return {maxReferences: 32};}, destroy() {destroyed.push('capabilities');}};
  }}, toPy(value) {return {value, destroy() {destroyed.push('converted');}};}};
  const context = {URL, ArrayBuffer, Uint8Array, self: {postMessage: reply => replies.push(reply)}, __py: py};
  // Script VM does not expose import.meta. Substitute only this static source
  // URL; replace runtime loading with the injectable bridge surrogate below.
  const source = readFileSync(new URL('../app/vision-worker.js', import.meta.url), 'utf8')
    .replaceAll('import.meta.url', JSON.stringify('https://local.example/app/vision-worker.js'));
  vm.runInNewContext(`${source}\nloadRuntime = async () => globalThis.__py;`, context);
  return {replies, calls, destroyed, send: data => context.self.onmessage({data})};
}

test('worker forwards explicit map-only context and preserves its controller ticket', async () => {
  const worker = harness();
  await worker.send({id: 1, type: 'init', maps: []});
  const ticket = {epoch: 3, sequence: 9};
  await worker.send({id: 2, type: 'analyze', context: 'map-only', mapId: 'erangel', ticket, rgba: new ArrayBuffer(8), width: 2, height: 1});
  assert.equal(worker.calls[0].context, 'map-only');
  assert.equal(worker.calls[0].mapId, 'erangel');
  assert.equal(worker.replies[1].type, 'result');
  assert.equal(worker.replies[1].ticket, ticket);
  assert.equal(worker.replies[1].position, null);
  assert.equal(worker.replies[1].zone, null);
  assert.equal(worker.destroyed.filter(name => name === 'converted').length, 1);
});

test('worker keeps legacy default/live and replay contexts unchanged', async () => {
  const worker = harness();
  await worker.send({id: 1, type: 'init', maps: []});
  for (const [index, context] of [undefined, 'live', 'replay'].entries())
    await worker.send({id: index + 2, type: 'analyze', context, rgba: new ArrayBuffer(4), width: 1, height: 1});
  assert.deepEqual(worker.calls.map(call => call.context), ['live', 'live', 'replay']);
  assert.ok(worker.calls.every(call => call.mapId === undefined), 'An absent map lock must become Python None, not jsnull');
  assert.ok(worker.replies.every(reply => reply.type !== 'error'));
});

test('worker accepts 32 references and rejects an over-capacity transaction before conversion', async () => {
  const worker = harness();
  await worker.send({id: 1, type: 'init', maps: []});
  const references = Array.from({length: 32}, (_, index) => ({mapId: `map-${index}`, rgba: new ArrayBuffer(4), width: 1, height: 1}));
  await worker.send({id: 2, type: 'references', references});
  assert.equal(worker.replies[1].type, 'references');
  assert.equal(worker.replies[1].count, 32);
  assert.equal(worker.calls[0].records.length, 32);
  await worker.send({id: 3, type: 'references', references: [...references, references[0]]});
  assert.equal(worker.replies[2].type, 'error');
  assert.match(worker.replies[2].reason, /at most 32/);
  assert.equal(worker.calls.length, 1, 'The rejected transaction must not replace the Python reference set');
  assert.equal(worker.destroyed.filter(name => name === 'converted').length, 1);
});
