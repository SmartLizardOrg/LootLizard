import test from 'node:test';
import assert from 'node:assert/strict';
import {validateMaps, validateCatalog, readBoundedJSON} from '../app/metadata.mjs';

const map = () => ({id: 'test-map', name: 'Test map', size_m: 8000, source: {license: 'MIT'},
  points: [{id: 'test-01', name: 'Test room', x: .2, y: .8}]});

test('a complete valid snapshot or explicit empty removal snapshot is accepted', () => {
  const snapshot = {schema_version: 1, revision: 'test-revision', maps: [map()]};
  assert.equal(validateCatalog(snapshot), snapshot);
  assert.deepEqual(validateCatalog({...snapshot, maps: []}).maps, []);
});

test('unsafe or coerced IDs and duplicate map/point identities are rejected', () => {
  for (const id of ['../escape', 'UPPERCASE', 123, null]) {
    assert.throws(() => validateMaps([{...map(), id}]));
    const value = map(); value.points[0].id = id;
    assert.throws(() => validateMaps([value]));
  }
  assert.throws(() => validateMaps([map(), map()]));
  const value = map(); value.points.push({...value.points[0]});
  assert.throws(() => validateMaps([value]));
});

test('non-object source and non-normalized coordinates are rejected', () => {
  for (const source of [[], null, 'MIT']) assert.throws(() => validateMaps([{...map(), source}]));
  for (const x of [-.01, 1.01, NaN, Infinity, '0.2']) {
    const value = map(); value.points[0].x = x;
    assert.throws(() => validateMaps([value]));
  }
});

test('invalid schema or revision cannot replace the current snapshot', () => {
  for (const revision of ['', '   ', 'x'.repeat(161), 123]) {
    assert.throws(() => validateCatalog({schema_version: 1, revision, maps: [map()]}));
  }
  assert.throws(() => validateCatalog({schema_version: 2, revision: 'known', maps: []}));
});

test('maps without bundled room coordinates are valid and do not invent a point', () => {
  const empty = {...map(), points: []};
  assert.deepEqual(validateMaps([empty])[0].points, []);
  assert.deepEqual(validateCatalog({schema_version: 1, revision: 'release', maps: [empty]}).maps[0].points, []);
});

test('location kinds are optional for legacy rooms and only known kinds are accepted', () => {
  const legacy=map();
  assert.equal(validateMaps([legacy])[0],legacy);
  assert.equal(Object.hasOwn(legacy.points[0],'kind'),false,'Validation must not mutate legacy records');
  for(const kind of ['secret_room','security_room','bear_cave','tunnel_entrance','supply_cache']){
    const value=map();value.points[0].kind=kind;
    assert.equal(validateMaps([value])[0].points[0].kind,kind);
  }
  for(const kind of [null,undefined,[],{},1,'SECRET_ROOM','unknown','constructor','__proto__']){
    const value=map();value.points[0].kind=kind;
    assert.throws(()=>validateMaps([value]),/Invalid location record/);
  }
});

test('bounded JSON rejects declared and streamed excess before publication', async () => {
  await assert.rejects(readBoundedJSON(new Response('{}', {headers: {'content-length': '999'}}), 20), /too large/);
  const stream = new ReadableStream({start(controller) {
    controller.enqueue(new TextEncoder().encode('{"long":"'));
    controller.enqueue(new TextEncoder().encode('x'.repeat(30) + '"}'));
    controller.close();
  }});
  await assert.rejects(readBoundedJSON(new Response(stream), 20), /too large/);
  await assert.rejects(readBoundedJSON(new Response('{}', {status: 404})), /HTTP 404/);
});

test('JSON decoding is UTF-8 strict and valid bounded content is returned', async () => {
  await assert.rejects(readBoundedJSON(new Response(new Uint8Array([0xff]))));
  const expected = {name: 'Próba'};
  assert.deepEqual(await readBoundedJSON(new Response(JSON.stringify(expected))), expected);
});
