import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {OCR_ASSETS, contextCropPlan, createMatchContextReader, fetchVerifiedOcrModel} from '../app/match-context-reader.mjs';

function frame(width = 320, height = 240) {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < data.length; i += 4) {data[i] = 80; data[i + 1] = 120; data[i + 2] = 160; data[i + 3] = 255;}
  return {width, height, data};
}
const word = (text = 'PLAY', bbox = {x0: 4, y0: 2, x1: 30, y1: 5}, confidence = 92) => ({text, bbox, confidence});
const nested = words => ({data: {blocks: [{paragraphs: [{lines: [{words}]}]}]}});
const deferred = () => {let resolve, reject; const promise = new Promise((a, b) => {resolve = a; reject = b;}); return {promise, resolve, reject};};

test('import and construction are lazy; a reusable reader performs bounded sequential crops', async () => {
  let factories = 0, stops = 0, concurrent = 0, maxConcurrent = 0;
  const images = [];
  const reader = createMatchContextReader({workerFactory: () => {
    factories++;
    return {terminate() {stops++;}, async recognize(image) {
      concurrent++; maxConcurrent = Math.max(maxConcurrent, concurrent); images.push(image);
      await Promise.resolve(); concurrent--;
      return nested([word()]);
    }};
  }});
  assert.deepEqual(reader.getState(), {busy: false, initialized: false, ready: false, version: '7.0.0'});
  assert.equal(factories, 0);
  const first = await reader.read(frame());
  assert.equal(first.status, 'ok');
  assert.equal(first.words.length, 4);
  assert.equal(images.length, 4);
  assert.equal(maxConcurrent, 1);
  await reader.read(frame());
  assert.equal(factories, 1, 'Later reads must reuse the same worker');
  assert.equal(images.length, 8);
  reader.terminate();
  assert.equal(stops, 1);
  assert.equal(reader.getState().initialized, false);
});

test('a concurrent read is skipped rather than queueing frames or creating another worker', async () => {
  const recognized = deferred();
  let factories = 0, reads = 0;
  const reader = createMatchContextReader({workerFactory: () => ({terminate() {}, recognize() {
    reads++; return recognized.promise;
  }, ready: (++factories, Promise.resolve())})});
  const first = reader.read(frame());
  const second = await reader.read(frame());
  assert.equal(second.reason, 'ocr-busy');
  assert.deepEqual(second.words, []);
  recognized.resolve(nested([]));
  await first;
  assert.equal(factories, 1);
  assert.equal(reads, 4);
  reader.terminate();
});

test('preparation is lazy, single-flight startup without image processing and only publishes readiness after initialization', async () => {
  let factories = 0, reads = 0;
  const initialized = deferred();
  const reader = createMatchContextReader({workerFactory: () => {
    factories++;
    return {ready: initialized.promise, terminate() {}, recognize() {reads++; return nested([word()]);}};
  }});
  assert.equal(factories, 0);
  const preparation = reader.prepare();
  assert.equal(reader.prepare(), preparation, 'Concurrent warmup callers share one operation');
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  assert.equal(factories, 1);
  assert.equal(reader.getState().ready, false);
  assert.equal(reader.getState().busy, false, 'Warmup is not a queued image read');
  assert.equal(reads, 0);
  initialized.resolve();
  assert.equal(await preparation, true);
  assert.equal(reader.getState().ready, true);
  assert.equal(await reader.prepare(), true);
  assert.equal(factories, 1);
  assert.equal(reads, 0, 'Warmup never invokes recognition');
  assert.equal((await reader.read(frame())).status, 'ok');
  assert.equal(factories, 1, 'A prepared worker is reused by the first actual read');
  assert.equal(reads, 4);
  reader.terminate();
  assert.equal(reader.getState().ready, false);
});

test('warmup deadline disposes its worker and resolves false without an unhandled rejection', async () => {
  let stops = 0;
  const reader = createMatchContextReader({initTimeoutMs: 8, workerFactory: () => ({
    ready: new Promise(() => {}), terminate() {stops++;}, recognize() {assert.fail('Warmup must not recognize');},
  })});
  assert.equal(await reader.prepare(), false);
  assert.equal(stops, 1);
  assert.equal(reader.getState().ready, false);
  assert.equal(reader.getState().initialized, false);
  const failed = createMatchContextReader({workerFactory: () => {throw Error('Initialization failed');}});
  assert.equal(await failed.prepare(), false);
  assert.equal(failed.getState().ready, false);
});

test('terminating warmup prevents a late initialization from republishing readiness or replacing a new worker', async () => {
  const initialized = deferred();
  let factories = 0, stopped = 0;
  const reader = createMatchContextReader({workerFactory: () => ({
    ready: ++factories === 1 ? initialized.promise : Promise.resolve(),
    terminate() {stopped++;}, recognize() {return nested([]);},
  })});
  const old = reader.prepare();
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  reader.terminate();
  assert.equal(await old, false);
  assert.equal(stopped, 1);
  assert.equal(reader.getState().ready, false);
  const next = reader.prepare();
  initialized.resolve();
  assert.equal(await next, true);
  assert.equal(reader.getState().ready, true);
  assert.equal(factories, 2);
  reader.terminate();
  assert.equal(stopped, 2);
});

test('stopping before the lazy factory starts avoids creating an obsolete worker', async () => {
  let factories = 0;
  const reader = createMatchContextReader({workerFactory: () => {factories++; throw Error('Should not start');}});
  const preparation = reader.prepare();
  reader.terminate();
  assert.equal(await preparation, false);
  assert.equal(factories, 0);
  assert.equal(reader.getState().ready, false);
});

test('crop geometry covers classification regions and native footer without overlap or unbounded allocations', () => {
  for (const [width, height] of [[320, 240], [1920, 1080], [2400, 1600], [1600, 2400]]) {
    const plan = contextCropPlan(width, height);
    assert.deepEqual(plan.map(crop => crop.id), ['upper', 'mode', 'actions', 'footer']);
    assert.ok(plan.reduce((sum, crop) => sum + crop.width * crop.height, 0) <= 700000);
    for (const crop of plan) {
      assert.ok(crop.x0 >= 0 && crop.y0 >= 0 && crop.x1 <= width && crop.y1 <= height);
      assert.ok(crop.x1 > crop.x0 && crop.y1 > crop.y0);
      assert.ok(crop.width <= crop.x1 - crop.x0 && crop.height <= crop.y1 - crop.y0, 'No upscaling');
    }
    for (let i = 1; i < plan.length; i++) assert.equal(plan[i - 1].y1, plan[i].y0, 'Text bands must not overlap and duplicate words');
    assert.equal(plan[3].y1, height);
    assert.ok(plan[3].y0 >= height * .965);
  }
  for (const dimensions of [[0, 240], [320, Infinity], [2401, 100], [2400, 2400], [true, 240]])
    assert.throws(() => contextCropPlan(...dimensions), /invalid-frame/);
});

test('word boxes map from each downsampled crop into full capture pixels and retain reading order', async () => {
  const image = frame(1920, 1080), plan = contextCropPlan(image.width, image.height);
  let index = 0;
  const reader = createMatchContextReader({workerFactory: () => ({terminate() {}, recognize(crop) {
    const record = plan[index++];
    assert.equal(crop.width, record.width); assert.equal(crop.height, record.height);
    assert.deepEqual(Array.from(crop.data.slice(0, 4)), [80, 120, 160, 255]);
    return nested([word('  RETURN\n TO LOBBY ', {x0: crop.width / 4, y0: crop.height / 4, x1: crop.width / 2, y1: crop.height / 2})]);
  }})});
  const result = await reader.read(image);
  assert.equal(result.width, image.width); assert.equal(result.height, image.height);
  result.words.forEach((entry, i) => {
    const crop = plan[i];
    assert.equal(entry.text, 'RETURN TO LOBBY');
    assert.equal(entry.confidence, 92);
    const expected = {x0: crop.x0 + (crop.x1 - crop.x0) / 4, y0: crop.y0 + (crop.y1 - crop.y0) / 4,
      x1: crop.x0 + (crop.x1 - crop.x0) / 2, y1: crop.y0 + (crop.y1 - crop.y0) / 2};
    for (const key of Object.keys(expected)) assert.ok(Math.abs(entry.bbox[key] - expected[key]) < 1e-8, key);
  });
  reader.terminate();
});

test('invalid frames and malformed words cannot fabricate context evidence', async () => {
  let factories = 0;
  const reader = createMatchContextReader({workerFactory: () => {
    factories++;
    return {terminate() {}, recognize() {return nested([
      word('', undefined), word('BAD', {x0: -1, y0: 0, x1: 3, y1: 3}),
      word('BAD', {x0: 0, y0: 0, x1: Infinity, y1: 3}), word('BAD', undefined, 101),
      word('BAD', {x0: 30, y0: 0, x1: 2, y1: 3}),
    ]);}};
  }});
  for (const value of [null, {...frame(), data: new Uint8Array(4)}, {...frame(), width: 99999}, {...frame(), data: new Uint8ClampedArray(4)}]) {
    assert.equal((await reader.read(value)).reason, 'ocr-invalid-frame');
  }
  assert.equal(factories, 0);
  assert.equal((await reader.read(frame())).reason, 'ocr-no-words');
  reader.terminate();
});

test('read timeout hard-terminates its worker and a later attempt creates a fresh one', async () => {
  let factories = 0, stops = 0;
  const reader = createMatchContextReader({timeoutMs: 8, workerFactory: () => {
    const number = ++factories;
    return {terminate() {stops++;}, recognize() {return number === 1 ? new Promise(() => {}) : nested([word()]);}};
  }});
  const result = await reader.read(frame());
  assert.equal(result.reason, 'ocr-read-timeout');
  assert.deepEqual(result.words, []);
  assert.equal(stops, 1);
  assert.equal(reader.getState().busy, false);
  assert.equal((await reader.read(frame())).status, 'ok');
  assert.equal(factories, 2);
  reader.terminate();
});

test('startup timeout terminates a known worker and disposes late asynchronous factories', async () => {
  let stopped = 0;
  const reader = createMatchContextReader({initTimeoutMs: 8, workerFactory: () => ({ready: new Promise(() => {}), terminate() {stopped++;}, recognize() {assert.fail('Not ready');}})});
  assert.equal((await reader.read(frame())).reason, 'ocr-startup-timeout');
  assert.equal(stopped, 1);
  const factory = deferred();
  const late = createMatchContextReader({initTimeoutMs: 8, workerFactory: () => factory.promise});
  assert.equal((await late.read(frame())).reason, 'ocr-startup-timeout');
  factory.resolve({terminate() {stopped++;}, recognize() {assert.fail('Expired worker');}});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(stopped, 2);
});

test('caller cancellation and explicit termination discard in-flight words without exposing OCR errors', async () => {
  const response = deferred(); let stopped = 0;
  const reader = createMatchContextReader({workerFactory: () => ({terminate() {stopped++;}, recognize() {return response.promise;}})});
  const controller = new AbortController();
  const result = reader.read(frame(), {signal: controller.signal});
  await Promise.resolve(); await Promise.resolve();
  controller.abort();
  assert.equal((await result).reason, 'ocr-cancelled');
  response.resolve(nested([word('PRIVATE PLAYER NAME')]));
  await Promise.resolve();
  assert.equal(stopped, 1);
  const failed = createMatchContextReader({workerFactory: () => {throw Error('PRIVATE PLAYER NAME');}});
  const error = await failed.read(frame());
  assert.equal(error.reason, 'ocr-unavailable');
  assert.equal(JSON.stringify(error).includes('PRIVATE'), false);
  const already = new AbortController(); already.abort();
  assert.equal((await failed.read(frame(), {signal: already.signal})).reason, 'ocr-cancelled');
});

test('model/runtime locations are immutable pinned official packages', () => {
  assert.ok(Object.isFrozen(OCR_ASSETS)); assert.ok(Object.isFrozen(OCR_ASSETS.model));
  assert.match(OCR_ASSETS.worker, /^https:\/\/cdn\.jsdelivr\.net\/npm\/tesseract\.js@7\.0\.0\/dist\/worker\.min\.js$/);
  assert.equal(OCR_ASSETS.core, 'https://cdn.jsdelivr.net/npm/tesseract.js-core@7.0.0');
  assert.match(OCR_ASSETS.model.url, /@tesseract\.js-data\/eng@1\.0\.0\/4\.0\.0_best_int\/eng\.traineddata\.gz$/);
  assert.equal(OCR_ASSETS.model.bytes, 2952873);
  assert.match(OCR_ASSETS.model.sha256, /^[0-9a-f]{64}$/);
});

test('model verification uses omitted credentials, HTTP cache and all reviewed bytes', async () => {
  const bytes = new Uint8Array(OCR_ASSETS.model.bytes);
  let digested = 0;
  const verified = await fetchVerifiedOcrModel({fetchImpl: async (url, options) => {
    assert.equal(url, OCR_ASSETS.model.url); assert.equal(options.credentials, 'omit');
    assert.equal(options.redirect, 'error'); assert.equal(options.cache, 'force-cache');
    return new Response(bytes);
  }, cryptoImpl: {subtle: {async digest(algorithm, input) {
    assert.equal(algorithm, 'SHA-256'); digested = input.byteLength;
    return Uint8Array.from(OCR_ASSETS.model.sha256.match(/../g), pair => parseInt(pair, 16)).buffer;
  }}}});
  assert.equal(verified.byteLength, OCR_ASSETS.model.bytes);
  assert.equal(digested, OCR_ASSETS.model.bytes);
  await assert.rejects(fetchVerifiedOcrModel({fetchImpl: async () => new Response(bytes), cryptoImpl: webcrypto}), /checksum-mismatch/);
});

test('model HTTP failures and size bounds cancel bodies before hashing or execution', async () => {
  let cancelled = 0;
  const response = headers => new Response(new ReadableStream({start(controller) {controller.enqueue(new Uint8Array(1));}, cancel() {cancelled++;}}), {headers});
  const neverHash = {subtle: {digest() {assert.fail('Unreviewed bytes must not be hashed');}}};
  await assert.rejects(fetchVerifiedOcrModel({fetchImpl: async () => response({'content-length': '3200001'}), cryptoImpl: neverHash}), /byte-limit/);
  assert.equal(cancelled, 1);
  const streamed = new Response(new ReadableStream({start(controller) {controller.enqueue(new Uint8Array(3200001));}, cancel() {cancelled++;}}));
  await assert.rejects(fetchVerifiedOcrModel({fetchImpl: async () => streamed, cryptoImpl: neverHash}), /byte-limit/);
  assert.equal(cancelled, 2);
  await assert.rejects(fetchVerifiedOcrModel({fetchImpl: async () => new Response(new Uint8Array(8)), cryptoImpl: neverHash}), /size-mismatch/);
  await assert.rejects(fetchVerifiedOcrModel({fetchImpl: async () => new Response(null, {status: 404}), cryptoImpl: neverHash}), /download-failed/);
});
