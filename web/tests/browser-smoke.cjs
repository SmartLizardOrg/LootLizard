/* Hosted CI only. Synthetic screen frames and official public map references. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn, spawnSync} = require('node:child_process');

if (process.env.GITHUB_ACTIONS !== 'true' || !process.env.RUNNER_TEMP) {
  throw new Error('The headless browser probe is restricted to hosted CI. Use the approved visible browser for local review.');
}
const {chromium} = require(process.env.LOOTLIZARD_PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../..');
const evidence = path.resolve(process.env.LOOTLIZARD_WEB_EVIDENCE || path.join(process.env.RUNNER_TEMP, 'lootlizard-web-evidence'));
const relative = path.relative(path.resolve(process.env.RUNNER_TEMP), evidence);
if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) throw new Error('Evidence must stay below RUNNER_TEMP.');
fs.mkdirSync(evidence, {recursive: true});
const base = 'http://127.0.0.1:8765';
const report = {status: 'running', steps: [], requests: [], console: [], pageErrors: []};
let server, browser, context, page, serverOutput = '';
const save = () => fs.writeFileSync(path.join(evidence, 'browser-report.json'), JSON.stringify(report, null, 2));
const deadline = setTimeout(() => { report.status = 'timeout'; save(); server?.kill(); process.exit(1); }, 8 * 60_000);
deadline.unref();

async function main() {
  const build = spawnSync(process.env.PYTHON || 'python', ['-B', 'scripts/build_web.py'], {cwd: root, windowsHide: true, encoding: 'utf8'});
  assert.equal(build.status, 0, `Static site build failed: ${build.stderr || build.stdout}`);
  server = spawn(process.env.PYTHON || 'python', ['-B', 'scripts/serve_web.py', '--port', '8765'],
    {cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe']});
  server.on('error', error => { report.serverError = String(error); });
  for (const stream of [server.stdout, server.stderr]) stream.on('data', value => { serverOutput = (serverOutput + value).slice(-100_000); });
  let up = false;
  for (let i = 0; i < 100; i++) {
    if (server.exitCode !== null) throw new Error('The static server exited before browser startup.');
    try { up = (await fetch(base + '/app/')).ok; } catch {}
    if (up) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert.ok(up, 'Loopback server did not become ready');
  browser = await chromium.launch({headless: true});
  context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  await context.tracing.start({screenshots: true, snapshots: true, sources: true});
  page = await context.newPage();
  page.setDefaultTimeout(30_000);
  page.on('console', message => report.console.push({type: message.type(), text: message.text().slice(0, 2500)}));
  page.on('pageerror', error => report.pageErrors.push(String(error)));
  page.on('request', request => report.requests.push({method: request.method(), url: request.url()}));
  await page.goto(base + '/app/?test=1&diagnostics=1', {waitUntil: 'domcontentloaded'});
  await page.waitForFunction(() => Boolean(window.lootLizard), null, {timeout: 30_000});
  page.setDefaultTimeout(240_000);
  const engine = await page.evaluate(async () => window.lootLizard.ready);
  page.setDefaultTimeout(30_000);
  const capabilities = engine.capabilities || engine;
  assert.equal(capabilities.sift, true, 'Actual WASM OpenCV SIFT must be exercised');
  assert.equal(capabilities.affine, true, 'Actual WASM affine estimators must be exercised');
  report.engine = engine;
  report.steps.push('real-pyodide-sift-and-affine-ready');
  report.defaultReferences = await page.evaluate(() => window.lootLizard.getState().referenceCount);
  assert.equal(report.defaultReferences, 2, 'Erangel and Taego references must load without user file import');
  report.steps.push('official-default-references-load-automatically');

  const workerResults = await page.evaluate(async () => {
    const {createDemo} = await import('/app/demo.mjs');
    const demo = createDemo();
    const worker = new Worker('/app/vision-worker.js', {type: 'module'});
    let sequence = 0;
    const pending = new Map();
    worker.onmessage = ({data}) => {
      const request = pending.get(data.id);
      if (!request) return;
      pending.delete(data.id);
      data.type === 'error' ? request.reject(new Error(data.reason)) : request.resolve(data);
    };
    worker.onerror = error => { for (const request of pending.values()) request.reject(new Error(error.message)); pending.clear(); };
    const rpc = (type, fields = {}) => new Promise((resolve, reject) => {
      const id = ++sequence;
      pending.set(id, {resolve, reject});
      worker.postMessage({id, type, ...fields});
    });
    const rgba = image => image.data.buffer.slice(image.data.byteOffset, image.data.byteOffset + image.data.byteLength);
    try {
      const ready = await rpc('init', {maps: [demo.map]});
      const loaded = await rpc('references', {references: [{mapId: demo.map.id, rgba: rgba(demo.reference),
        width: demo.reference.width, height: demo.reference.height}]});
      const results = [];
      for (const [index, image] of demo.frames.entries()) {
        results.push(await rpc('analyze', {rgba: rgba(image), width: image.width, height: image.height,
          context: 'live', ticket: {epoch: 1, sequence: index + 1}}));
      }
      return {ready, loaded, map: demo.map, results};
    } finally { worker.terminate(); }
  });
  assert.equal(workerResults.ready.version, '314.0.7');
  assert.equal(workerResults.loaded.count, 1);
  assert.equal(workerResults.results.length, 3);
  workerResults.results.forEach((result, index) => {
    assert.deepEqual(result.ticket, {epoch: 1, sequence: index + 1}, 'Object frame ticket must survive worker/Python boundaries exactly');
  });
  for (const index of [0, 2]) {
    const result = workerResults.results[index];
    assert.equal(result.registration?.mapId, workerResults.map.id);
    assert.equal(result.points.length, workerResults.map.points.length);
    for (const point of workerResults.map.points) {
      const projected = result.points.find(candidate => candidate.id === point.id);
      assert.equal(projected?.visible, true);
      assert.ok(Math.hypot(projected.imageX - (160 + point.x * 640), projected.imageY - (40 + point.y * 640)) < 5,
        'Synthetic known transform must place every target within five image pixels');
    }
  }
  const gameplay = workerResults.results[1];
  assert.equal(gameplay.registration, null);
  assert.equal(gameplay.position, null);
  assert.equal(gameplay.zone, null);
  assert.deepEqual(gameplay.points, []);
  report.worker = workerResults;
  report.steps.push('real-cv-map-gameplay-rejection-map-return-and-projection');

  await page.locator('#load-demo').click();
  await page.waitForFunction(() => window.lootLizard.getState().mapId === 'demo', null, {timeout: 60_000});
  assert.ok(await page.locator('#target-list tr').count() > 0);
  await page.screenshot({path: path.join(evidence, 'synthetic-demo.png'), fullPage: true});
  report.demoState = await page.evaluate(() => window.lootLizard.getState());
  report.steps.push('demo-button-renders-real-cv-targets');

  const stale = await page.evaluate(async () => {
    const {createDemo} = await import('/app/demo.mjs');
    const {mapFrame} = createDemo();
    const pending = window.lootLizard.analyzeImageData(mapFrame, {source: 'demo'});
    window.lootLizard.stop();
    await pending;
    return window.lootLizard.getState();
  });
  assert.equal(stale.mapId, null);
  assert.deepEqual(stale.points, []);
  assert.equal(stale.sharing, false);
  assert.equal(await page.locator('#target-list tr').count(), 0);
  report.stoppedState = stale;
  report.steps.push('immediate-stop-cancels-async-session-start');

  const inflight = await page.evaluate(async () => {
    const {createDemo} = await import('/app/demo.mjs');
    let scanningState;
    const stopped = new Promise(resolve => {
      const observer = new MutationObserver(() => {
        if (window.lootLizard.getState().phase !== 'scanning') return;
        observer.disconnect();
        scanningState = window.lootLizard.getState();
        // request() posts in its already-enqueued Promise microtask. Queue Stop
        // behind that post, before a worker reply can run as a new event task.
        queueMicrotask(() => { window.lootLizard.stop(); resolve(); });
      });
      observer.observe(document.querySelector('#recognition-status'), {childList: true, characterData: true, subtree: true});
    });
    const pending = window.lootLizard.analyzeImageData(createDemo().mapFrame, {source: 'demo'});
    await Promise.race([stopped, new Promise((_, reject) => setTimeout(() => reject(Error('No in-flight scanning phase observed')), 15_000))]);
    const reply = await pending;
    return {scanningState, reply, stopped: window.lootLizard.getState()};
  });
  assert.equal(inflight.scanningState.phase, 'scanning');
  assert.equal(inflight.scanningState.mapId, null);
  assert.deepEqual(inflight.scanningState.points, []);
  assert.equal(inflight.reply, null);
  assert.equal(inflight.stopped.mapId, null);
  assert.deepEqual(inflight.stopped.points, []);
  report.inflightStop = inflight;
  report.steps.push('posted-worker-request-cannot-restore-geometry-after-stop');

  // A real synthetic MediaStream follows the same controller path without
  // granting or bypassing getDisplayMedia permission. Available only on the
  // loopback ?test=1 page, never a normal site/capture-picker replacement.
  await page.evaluate(async () => {
    const {createDemo} = await import('/app/demo.mjs');
    const demo = createDemo(), frame = demo.mapFrame;
    const canvas = document.createElement('canvas');
    canvas.width = frame.width; canvas.height = frame.height;
    canvas.getContext('2d').putImageData(frame, 0, 0);
    const stream = canvas.captureStream(2);
    window.__syntheticCapture = {canvas, stream, frames: demo.frames, scans: []};
    const observer = new MutationObserver(() => {
      const state = window.lootLizard.getState();
      if (state.phase === 'scanning') window.__syntheticCapture.scans.push(state);
    });
    observer.observe(document.querySelector('#recognition-status'), {childList: true, characterData: true, subtree: true});
    window.__syntheticCapture.observer = observer;
    await window.lootLizard.startTestStream(stream, {demo: true});
  });
  const otherTab = await context.newPage();
  await otherTab.goto('about:blank');
  await otherTab.bringToFront();
  await page.waitForFunction(() => {
    const state = window.lootLizard.getState();
    return state.sharing && state.mapId === 'demo' && state.points.length > 0;
  }, null, {timeout: 60_000});
  report.passiveStreamState = await page.evaluate(() => window.lootLizard.getState());
  await page.evaluate(() => {
    const fixture = window.__syntheticCapture;
    fixture.scans.length = 0;
    fixture.canvas.getContext('2d').putImageData(fixture.frames[1], 0, 0);
    fixture.stream.getVideoTracks()[0].requestFrame?.();
  });
  await page.waitForFunction(() => {
    const state = window.lootLizard.getState();
    return state.sharing && state.phase === 'unknown' && state.mapId === null && state.points.length === 0;
  }, null, {timeout: 60_000});
  const gameplayUI = await page.evaluate(() => ({state: window.lootLizard.getState(), scans: window.__syntheticCapture.scans}));
  assert.ok(gameplayUI.scans.length > 0, 'Automatic stream must actually process the changed frame');
  assert.ok(gameplayUI.scans.every(state => state.mapId === null && state.points.length === 0), 'A newer displayed frame must never carry old geometry while scanning');
  assert.equal(await page.locator('#target-list tr').count(), 0);
  await page.evaluate(() => {
    const fixture = window.__syntheticCapture;
    fixture.canvas.getContext('2d').putImageData(fixture.frames[2], 0, 0);
    fixture.stream.getVideoTracks()[0].requestFrame?.();
  });
  await page.waitForFunction(() => window.lootLizard.getState().mapId === 'demo', null, {timeout: 60_000});
  report.streamGameplay = gameplayUI;
  report.streamMapReturn = await page.evaluate(() => window.lootLizard.getState());
  report.steps.push('automatic-stream-map-gameplay-map-and-no-old-geometry-while-scanning');
  await page.evaluate(() => {
    const track = window.__syntheticCapture.stream.getVideoTracks()[0];
    track.stop();
    // MediaStreamTrack.stop() intentionally does not fire 'ended'. Dispatch the
    // event here to model the browser's user-driven Stop sharing notification.
    track.dispatchEvent(new Event('ended'));
    window.__syntheticCapture.observer.disconnect();
  });
  await page.waitForFunction(() => !window.lootLizard.getState().sharing);
  const ended = await page.evaluate(() => window.lootLizard.getState());
  assert.equal(ended.mapId, null);
  assert.deepEqual(ended.points, []);
  assert.equal(ended.position, null);
  assert.equal(ended.zone, null);
  report.endedState = ended;
  report.steps.push('synthetic-stream-automatic-scan-and-ended-clears-state');

  await page.bringToFront();
  await page.locator('#settings-panel > summary').click();
  assert.equal(await page.locator('#performance-diagnostics').isVisible(), true);
  await page.evaluate(async () => {
    const fixture = window.__syntheticCapture;
    fixture.stream = fixture.canvas.captureStream(2);
    await window.lootLizard.startTestStream(fixture.stream, {demo: true});
  });
  await page.waitForFunction(() => window.lootLizard.getState().mapId === 'demo', null, {timeout: 60_000});
  await page.locator('#capture-work').selectOption('capture-only');
  const modeCleared = await page.evaluate(() => ({state: window.lootLizard.getState(),
    mode: window.lootLizard.getPerformance().mode}));
  assert.equal(modeCleared.mode, 'capture-only');
  assert.equal(modeCleared.state.sharing, true, 'Pausing processing must retain the approved capture stream');
  assert.equal(modeCleared.state.mapId, null);
  assert.deepEqual(modeCleared.state.points, []);
  assert.equal(modeCleared.state.position, null);
  assert.equal(modeCleared.state.zone, null);
  assert.equal(await page.locator('#target-list tr').count(), 0);

  await page.locator('#capture-work').selectOption('full');
  const inflightMode = await page.evaluate(async () => {
    const {createDemo} = await import('/app/demo.mjs');
    let scanningState;
    const switched = new Promise(resolve => {
      const observer = new MutationObserver(() => {
        if (window.lootLizard.getState().phase !== 'scanning') return;
        observer.disconnect();
        scanningState = window.lootLizard.getState();
        // As in the Stop test, queue the real control's change event after the
        // already-enqueued worker post, before its reply can run as a task.
        queueMicrotask(() => {
          const control = document.querySelector('#capture-work');
          control.value = 'capture-only';
          control.dispatchEvent(new Event('change', {bubbles: true}));
          resolve();
        });
      });
      observer.observe(document.querySelector('#recognition-status'), {childList: true, characterData: true, subtree: true});
    });
    const pending = window.lootLizard.analyzeImageData(createDemo().mapFrame, {source: 'demo'});
    await Promise.race([switched, new Promise((_, reject) => setTimeout(() => reject(Error('No in-flight mode switch observed')), 15_000))]);
    const reply = await pending;
    return {scanningState, reply, state: window.lootLizard.getState(),
      mode: window.lootLizard.getPerformance().mode};
  });
  assert.equal(inflightMode.scanningState.phase, 'scanning');
  assert.equal(inflightMode.mode, 'capture-only');
  assert.equal(inflightMode.reply, null, 'A worker reply invalidated by a diagnostic mode change must be discarded');
  assert.equal(inflightMode.state.mapId, null);
  assert.deepEqual(inflightMode.state.points, []);
  assert.equal(inflightMode.state.position, null);
  assert.equal(inflightMode.state.zone, null);
  assert.equal(await page.locator('#target-list tr').count(), 0);
  report.modeCleared = modeCleared;
  report.inflightMode = inflightMode;
  report.steps.push('diagnostic-mode-clears-map-and-rejects-in-flight-worker-geometry');

  await page.locator('#capture-work').selectOption('full');
  await page.locator('#load-demo').click();
  await page.waitForFunction(() => window.lootLizard.getState().mapId === 'demo', null, {timeout: 60_000});
  await page.evaluate(async () => {
    const {createDemo} = await import('/app/demo.mjs');
    const {mapFrame} = createDemo();
    const canvas = document.createElement('canvas');
    canvas.width = mapFrame.width; canvas.height = mapFrame.height;
    canvas.getContext('2d').putImageData(mapFrame, 0, 0);
    const stream = canvas.captureStream(2);
    // Observe actual worker traffic, not just the timing fields which the
    // controller chooses to emit. This leaves real worker results untouched.
    const originalPost = Worker.prototype.postMessage;
    const probe = {canvas, stream, originalPost, analyzePosts: [], startEpochMs: performance.timeOrigin + performance.now()};
    window.__noReferenceCapture = probe;
    Worker.prototype.postMessage = function(message) {
      if (message?.type === 'analyze') probe.analyzePosts.push({id: message.id, rgbaBytes: message.rgba?.byteLength || 0});
      return Reflect.apply(originalPost, this, arguments);
    };
    // A fresh browser context has no imported references. Explicitly avoid the
    // synthetic reference used by the earlier automatic stream tests.
    await window.lootLizard.startTestStream(stream, {demo: false, withoutReferences: true});
  });
  await page.waitForFunction(() => {
    const state = window.lootLizard.getState(), probe = window.__noReferenceCapture;
    return state.sharing && state.phase === 'unknown' && window.lootLizard.getPerformance().events.some(
      event => event.path === 'no-references' && event.epochMs >= probe.startEpochMs);
  }, null, {timeout: 60_000});
  const noReferences = await page.evaluate(() => {
    const probe = window.__noReferenceCapture;
    return {state: window.lootLizard.getState(), analyzePosts: probe.analyzePosts,
      scans: window.lootLizard.getPerformance().events.filter(event => event.type === 'scan' && event.epochMs >= probe.startEpochMs)};
  });
  assert.equal(noReferences.state.mapId, null, 'The earlier demo geometry must be cleared');
  assert.deepEqual(noReferences.state.points, []);
  assert.equal(noReferences.state.position, null);
  assert.equal(noReferences.state.zone, null);
  assert.deepEqual(noReferences.analyzePosts, [], 'An empty reference library must not transfer screenshots to the worker');
  assert.ok(noReferences.scans.length > 0, 'The live synthetic screen must actually be sampled');
  for (const scan of noReferences.scans) {
    assert.equal(scan.path, 'no-references');
    assert.ok(Number.isFinite(scan.captureMs) && scan.captureMs >= 0);
    assert.equal(Object.hasOwn(scan, 'transferCopyMs'), false);
    assert.equal(Object.hasOwn(scan, 'workerRoundTripMs'), false);
    assert.equal(Object.hasOwn(scan, 'python'), false);
  }
  assert.equal(await page.locator('#target-list tr').count(), 0);
  await page.evaluate(() => {
    window.lootLizard.stop();
    Worker.prototype.postMessage = window.__noReferenceCapture.originalPost;
    delete window.__noReferenceCapture;
  });
  report.noReferences = noReferences;
  report.steps.push('empty-reference-screen-fast-path-samples-without-worker-transfer-or-stale-geometry');
  assert.ok(report.requests.every(request => ['GET', 'HEAD'].includes(request.method)), 'No image upload request may be issued');
  assert.deepEqual(report.pageErrors, [], 'No unhandled main-page error');
  report.status = 'passed';
}

main().catch(async error => {
  report.status = 'failed'; report.error = error.stack || String(error);
  if (page) await page.screenshot({path: path.join(evidence, 'failure.png'), fullPage: true}).catch(() => {});
  process.exitCode = 1;
}).finally(async () => {
  clearTimeout(deadline);
  save();
  if (context) await context.tracing.stop({path: path.join(evidence, 'trace.zip')}).catch(() => {});
  if (browser) await browser.close();
  server?.kill();
  fs.writeFileSync(path.join(evidence, 'server.log'), serverOutput);
  console.log(JSON.stringify({status: report.status, steps: report.steps, evidence}));
});
