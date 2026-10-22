import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {AUTOMATIC_REFERENCES, fetchReference, loadAutomaticReferences} from '../app/automatic-references.mjs';

const png = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 1]);
const response = (bytes = png, options = {}) => new Response(bytes, {headers: {'content-type': 'image/png'}, ...options});
const digestBytes = hash => Uint8Array.from(hash.match(/../g), byte => parseInt(byte, 16)).buffer;
const trustedDigest = record => ({subtle: {async digest(algorithm, bytes) {
  assert.equal(algorithm, 'SHA-256');
  assert.deepEqual(bytes, png);
  return digestBytes(record.sha256);
}}});

test('automatic references are immutable bundled assets for all eleven distinct official maps', () => {
  assert.deepEqual(AUTOMATIC_REFERENCES.map(record => record.mapId), ['erangel', 'miramar', 'sanhok', 'vikendi', 'karakin', 'paramo', 'haven', 'taego', 'deston', 'rondo', 'training']);
  assert.ok(Object.isFrozen(AUTOMATIC_REFERENCES));
  for (const record of AUTOMATIC_REFERENCES) {
    assert.ok(Object.isFrozen(record));
    const url = new URL(record.url);
    assert.equal(url.origin, new URL(import.meta.url).origin);
    assert.ok(url.pathname.endsWith(`/app/map-assets/${record.mapId}.png`));
    assert.equal(url.search, '');
    assert.match(record.sha256, /^[a-f0-9]{64}$/);
    assert.equal(record.width, 819);
    assert.equal(record.height, record.width);
  }
});

test('every bundled PNG matches its provenance manifest and the runtime checksum', async () => {
  const manifest = JSON.parse(await readFile(new URL('../app/map-assets/manifest.json', import.meta.url), 'utf8'));
  assert.equal(manifest.references.length, 11);
  assert.equal(manifest.source.commit, '32b13b51128b8d8909ae5e77f3b833e01230b24d');
  for (const record of AUTOMATIC_REFERENCES) {
    const source = manifest.references.find(item => item.mapId === record.mapId);
    assert.equal(source.sha256, record.sha256);
    assert.match(source.source_url, /^https:\/\/raw\.githubusercontent\.com\/pubg\/api-assets\/32b13b51128b8d8909ae5e77f3b833e01230b24d\/Assets\/Maps\/[A-Za-z0-9_]+\.png$/);
    const bytes = await readFile(new URL(record.url));
    assert.equal(bytes.length, source.bytes);
    assert.deepEqual(Array.from(bytes.subarray(0, 8)), [137, 80, 78, 71, 13, 10, 26, 10]);
    assert.equal(bytes.readUInt32BE(16), record.width);
    assert.equal(bytes.readUInt32BE(20), record.height);
    const hash = Buffer.from(await webcrypto.subtle.digest('SHA-256', bytes)).toString('hex');
    assert.equal(hash, record.sha256);
  }
});

test('fetch verifies the complete byte sequence and omits credentials', async () => {
  const record = AUTOMATIC_REFERENCES[0];
  const blob = await fetchReference(record, {cryptoImpl: trustedDigest(record), fetchImpl: async (url, options) => {
    assert.equal(url, record.url);
    assert.equal(options.credentials, 'omit');
    assert.equal(options.redirect, 'error');
    assert.equal(options.cache, 'no-cache');
    assert.ok(options.signal instanceof AbortSignal);
    return response();
  }});
  assert.equal(blob.type, 'image/png');
  assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), png);
});

test('a modified URL, hash, or unknown map cannot trigger a network request', async () => {
  let fetches = 0;
  const options = {fetchImpl: async () => {fetches++; return response();}, cryptoImpl: webcrypto};
  for (const record of [
    {...AUTOMATIC_REFERENCES[0], url: 'https://unreviewed.example/map.png'},
    {...AUTOMATIC_REFERENCES[0], sha256: '0'.repeat(64)},
    {...AUTOMATIC_REFERENCES[0], mapId: 'custom'},
  ]) await assert.rejects(fetchReference(record, options), /Unknown automatic reference/);
  assert.equal(fetches, 0);
});

test('real SHA-256 rejects bytes that differ from the reviewed official image', async () => {
  await assert.rejects(fetchReference(AUTOMATIC_REFERENCES[0], {fetchImpl: async () => response(), cryptoImpl: webcrypto}), /checksum mismatch/);
});

test('HTTP failure, wrong MIME, and invalid PNG signatures are rejected', async () => {
  const record = AUTOMATIC_REFERENCES[0];
  for (const [makeResponse, message] of [
    [() => response(null, {status: 404}), /HTTP 404/],
    [() => response(png, {headers: {'content-type': 'text/html'}}), /not a PNG/],
    [() => response(new Uint8Array([1, 2, 3])), /not a PNG/],
  ]) await assert.rejects(fetchReference(record, {fetchImpl: async () => makeResponse(), cryptoImpl: webcrypto}), message);
});

test('declared and streamed bodies above the byte bound are rejected before hashing', async () => {
  const record = AUTOMATIC_REFERENCES[0];
  const noDigest = {subtle: {digest() {assert.fail('Oversized bytes must not be hashed');}}};
  let downloadSignal;
  await assert.rejects(fetchReference(record, {cryptoImpl: noDigest, fetchImpl: async (_url, options) => {
    downloadSignal = options.signal;
    return response(png, {headers: {'content-type': 'image/png', 'content-length': '2000001'}});
  }}), /too large/);
  assert.equal(downloadSignal.aborted, true);
  let cancelled = false;
  const stream = new ReadableStream({start(controller) {
    controller.enqueue(png);
    controller.enqueue(new Uint8Array(2_000_000));
  }, cancel() {cancelled = true;}});
  await assert.rejects(fetchReference(record, {cryptoImpl: noDigest, fetchImpl: async () => response(stream)}), /too large/);
  assert.equal(cancelled, true);
});

test('caller cancellation propagates to the fetch signal', async () => {
  const controller = new AbortController();
  controller.abort(new Error('Cancelled by caller'));
  await assert.rejects(fetchReference(AUTOMATIC_REFERENCES[0], {signal: controller.signal, cryptoImpl: webcrypto, fetchImpl: async (_url, options) => {
    assert.equal(options.signal.aborted, true);
    throw options.signal.reason;
  }}), /Cancelled by caller/);
});

test('loader skips unknown map IDs and already available references', async () => {
  const result = await loadAutomaticReferences({knownMapIds: ['erangel', 'unreviewed'], existingMapIds: ['erangel'],
    fetchImpl: async () => assert.fail('No reference needs downloading'), decode: async () => assert.fail('No image needs decoding')});
  assert.deepEqual(result, {loaded: [], failures: []});
});

test('download failure is isolated per map and successful PNGs reach the decoder', async () => {
  const taego = AUTOMATIC_REFERENCES.find(record => record.mapId === 'taego');
  let decoded = 0;
  const image = {width: 819, height: 819};
  const result = await loadAutomaticReferences({knownMapIds: ['erangel', 'taego'], cryptoImpl: trustedDigest(taego),
    fetchImpl: async url => url === taego.url ? response() : response(null, {status: 503}),
    decode: async blob => {decoded++; assert.equal(blob.type, 'image/png'); return image;}});
  assert.equal(decoded, 1);
  assert.deepEqual(result.loaded, [{mapId: 'taego', image}]);
  assert.deepEqual(result.failures, [{mapId: 'erangel', error: 'Automatic reference HTTP 503'}]);
});

test('image decode failure is reported without discarding other maps', async () => {
  let fetchIndex = 0;
  const result = await loadAutomaticReferences({knownMapIds: ['erangel', 'taego'],
    fetchImpl: async () => {fetchIndex++; return response();},
    cryptoImpl: {subtle: {async digest() {return digestBytes(AUTOMATIC_REFERENCES.find(record => record.mapId === (fetchIndex === 1 ? 'erangel' : 'taego')).sha256);}}},
    decode: async () => {if (fetchIndex === 1) throw Error('Invalid image dimensions'); return {width: 819, height: 819};}});
  assert.deepEqual(result.loaded.map(record => record.mapId), ['taego']);
  assert.deepEqual(result.failures, [{mapId: 'erangel', error: 'Invalid image dimensions'}]);
});
