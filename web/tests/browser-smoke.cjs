/* Hosted CI only. Synthetic screen frames and bundled official map references. */
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
const deadline = setTimeout(() => { report.status = 'timeout'; save(); server?.kill(); process.exit(1); }, 12 * 60_000);
deadline.unref();

// Observe the rendered interface independently of the controller's state API.
// Hidden ancestors count. During gameplay the central bitmap must stay paired
// with its retained map registration; Stop/reset must still remove it.
async function readMapView() {
  return page.evaluate(() => {
    const visible = element => {
      if (!element || element.hidden || !element.getClientRects().length || getComputedStyle(element).visibility === 'hidden') return false;
      // Chromium may report layout rectangles for children of closed details.
      // The disclosure summary itself remains visible; its content does not.
      for (let parent = element.parentElement; parent; parent = parent.parentElement)
        if (parent.tagName === 'DETAILS' && !parent.open && !parent.querySelector(':scope > summary')?.contains(element)) return false;
      return typeof element.checkVisibility !== 'function' || element.checkVisibility({visibilityProperty: true});
    };
    const main = document.querySelector('#map-canvas');
    const preview = document.querySelector('#source-preview');
    const connect = document.querySelector('#connect-source');
    const pixelHash = canvas => {
      if (!canvas?.width || !canvas?.height) return null;
      const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      let hash = 2166136261;
      for (const value of pixels) hash = Math.imul(hash ^ value, 16777619);
      return (hash >>> 0).toString(16);
    };
    return {
      view: document.querySelector('#map-stage')?.dataset.view || null,
      title: document.querySelector('#stage-title')?.textContent.trim() || '',
      main: {visible: visible(main), width: main?.width || 0, height: main?.height || 0, pixelHash: pixelHash(main)},
      retainedBannerVisible: visible(document.querySelector('#retained-banner')),
      targetCount: document.querySelectorAll('#target-list tr').length,
      sourcePanelVisible: visible(document.querySelector('#source-panel')),
      sourceDetailsOpen: Boolean(document.querySelector('#source-details')?.open),
      reset: {visible: visible(document.querySelector('#reset-match')),
        insideDisclosure: Boolean(document.querySelector('#reset-match')?.closest('#source-details')),
        disabled: document.querySelector('#reset-match')?.disabled ?? true},
      preview: {visible: visible(preview), width: preview?.width || 0, height: preview?.height || 0,
        centerPixel: preview?.width && preview?.height ? Array.from(preview.getContext('2d').getImageData(
          Math.floor(preview.width / 2), Math.floor(preview.height / 2), 1, 1).data) : []},
      connect: {visible: visible(connect), disabled: connect?.disabled ?? true},
    };
  });
}

function assertCroppedMap(view) {
  assert.equal(view.view, 'map', 'Only a verified map may occupy the central map view');
  assert.equal(view.main.visible, true, 'A recognized map must be visible in the main stage');
  // The original fixture is 960 x 720. Its registered full map is the square
  // from (160, 40) to (800, 680); allow integer rounding of the fitted transform.
  assert.ok(Math.abs(view.main.width - 640) <= 4, `Expected a map crop near 640 pixels, got ${view.main.width}`);
  assert.ok(Math.abs(view.main.height - 640) <= 4, `Expected a map crop near 640 pixels, got ${view.main.height}`);
  assert.ok(Math.abs(view.main.width - view.main.height) <= 4, 'The full fixture map must stay square');
}

function assertSourcePreview(view) {
  assert.equal(view.sourcePanelVisible, true, 'An active shared source needs its small confirmation panel');
  assert.equal(view.sourceDetailsOpen, true);
  assert.equal(view.preview.visible, true, 'The shared-source preview must remain visible independently of map recognition');
  assert.ok(view.preview.width > 0 && view.preview.width <= 240, 'Preview bitmap width must be bounded before drawing');
  assert.ok(view.preview.height > 0 && view.preview.height <= 135, 'Preview bitmap height must be bounded before drawing');
  assert.ok(Math.abs(view.preview.width / view.preview.height - 960 / 720) < .02,
    'The small preview must preserve the 4:3 source aspect ratio');
  assert.equal(view.preview.centerPixel[3], 255, 'The source preview must contain an actual sampled frame');
}

function assertCollapsedSource(view) {
  assert.equal(view.sourcePanelVisible, true);
  assert.equal(view.sourceDetailsOpen, false, 'The first recognized map must collapse the source preview');
  assert.equal(view.preview.visible, false, 'Closed details must actually hide the preview');
  assert.equal(view.reset.visible, true, 'Reset match must remain available outside the closed preview');
  assert.equal(view.reset.insideDisclosure, false);
}

function assertMapOnlyState(state) {
  assert.equal(state.position, null, 'The player view must not infer a player position');
  assert.equal(state.zone, null, 'The player view must not infer a safe circle');
}

function assertStoppedView(view) {
  assert.equal(view.main.visible, false, 'Stopping must hide the old recognized map bitmap');
  assert.equal(view.sourcePanelVisible, false, 'Stopping must hide the source confirmation panel');
  assert.equal(view.preview.visible, false, 'Stopping must hide the source preview');
  assert.equal(view.retainedBannerVisible, false, 'Stopping must hide the retained-map notice');
  assert.notEqual(view.view, 'map', 'Stopped geometry must not leave a recognized-map presentation');
}

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
  context.on('request', request => report.requests.push({method: request.method(), url: request.url()}));
  await page.goto(base + '/app/?test=1', {waitUntil: 'domcontentloaded'});
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
  assert.equal(report.defaultReferences, 11, 'All ten battle-royale maps and Training must load from bundled assets');
  assert.equal(capabilities.maxReferences, 32);
  report.steps.push('eleven-bundled-map-references-load-without-external-image-downloads');
  assert.equal(await page.locator('#scan-interval').inputValue(), '1000');
  assert.equal((await page.evaluate(() => window.lootLizard.getState())).interval, 1000);
  const intervals = await page.locator('#scan-interval option').evaluateAll(options => options.map(option => option.value));
  assert.deepEqual(intervals, ['500', '1000', '2000', '5000', '10000']);
  await page.locator('#settings-panel > summary').click();
  for (const value of intervals) {
    await page.locator('#scan-interval').selectOption(value);
    const preference = await page.evaluate(() => ({state: window.lootLizard.getState(),
      stored: JSON.parse(localStorage.getItem('lootlizard.web.preferences.v1')),
      rate: window.lootLizard.getPerformance().requestedFrameRate}));
    assert.equal(preference.state.interval, Number(value));
    assert.equal(preference.stored.interval, Number(value));
    assert.equal(preference.rate, 1000 / Number(value));
  }
  await page.locator('#language-select').selectOption('hu');
  assert.equal((await page.evaluate(() => window.lootLizard.getState())).sharing, false, 'Preference reload checks must never interrupt a live capture');
  await page.reload({waitUntil: 'domcontentloaded'});
  await page.waitForFunction(() => Boolean(window.lootLizard), null, {timeout: 30_000});
  await page.evaluate(async () => window.lootLizard.ready);
  assert.equal(await page.locator('#scan-interval').inputValue(), '10000');
  assert.equal(await page.locator('#language-select').inputValue(), 'hu');
  assert.equal(await page.locator('html').getAttribute('lang'), 'hu');
  await page.locator('#settings-panel > summary').click();
  await page.locator('#language-select').selectOption('en');
  await page.locator('#scan-interval').selectOption('1000');
  await page.locator('#settings-panel > summary').click();
  report.steps.push('all-five-check-intervals-and-language-persist-across-stopped-page-reload');

  const production = await context.newPage();
  try {
    await production.goto(base + '/app/', {waitUntil: 'domcontentloaded'});
    await production.waitForFunction(() => !document.querySelector('#connect-source').disabled, null, {timeout: 240_000});
    assert.equal(await production.evaluate(() => typeof window.lootLizard), 'undefined', 'The synthetic test API must not be exposed on a normal player page');
    assert.equal(await production.locator('#load-demo, #open-image, #reference-file, #reference-map, #replay-mode, #capture-work, #performance-diagnostics, #engine-status, #metadata-status, #position-status, #inside-count').count(), 0);
    assert.equal(await production.locator('.targets-table th').count(), 2);
    const text = await production.locator('body').innerText();
    assert.doesNotMatch(text, /Pyodide|OpenCV|SIFT|WASM|RGBA|canonical|metadata|Load demo|Local performance diagnostics|identity unverified|distances unavailable/i,
      'The player interface must describe its task without developer/runtime details');
    report.productionInterface = {testApiAbsent: true, targetColumns: 2, developerControlsAbsent: true};
  } finally {await production.close();}
  await page.bringToFront();
  report.steps.push('normal-player-page-has-no-test-api-demo-controls-or-technical-runtime-copy');
  // The real default was verified above. Controlled video fixtures use a
  // slower supported cadence so a completed map remains observable between
  // expensive WASM scans rather than immediately entering the next scan.
  await page.locator('#settings-panel > summary').click();
  await page.locator('#scan-interval').selectOption('5000');
  await page.locator('#settings-panel > summary').click();
  assert.equal((await page.evaluate(() => window.lootLizard.getState())).interval, 5000);
  report.controlledFixtureIntervalMs = 5000;
  report.steps.push('controlled-synthetic-fixtures-use-five-second-checks-after-default-verification');
  const localOCR = await page.evaluate(async () => {
    const {createMatchContextReader} = await import('/app/match-context-reader.mjs');
    const {classifyMatchContext} = await import('/app/match-context.mjs');
    const canvas = document.createElement('canvas');
    canvas.width = 1200; canvas.height = 800;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#111820'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#ffffff'; ctx.font = 'bold 32px Arial';
    ctx.fillText('PLAY    CAREER    CUSTOMIZE    WORKSHOP    STORE', 32, 72);
    ctx.fillText('NORMAL', 32, 560);
    ctx.fillText('PLAY', 32, 710);
    const reader = createMatchContextReader({initTimeoutMs: 45_000, timeoutMs: 12_000});
    let observation, classification;
    try {
      observation = await reader.read(ctx.getImageData(0, 0, canvas.width, canvas.height));
      classification = classifyMatchContext(observation);
    } finally { reader.terminate(); }
    // Keep arbitrary recognized text out of test evidence, as in the app.
    return {status: observation.status, wordCount: observation.words?.length || 0,
      context: classification.context, reason: observation.reason, readerState: reader.getState()};
  });
  assert.equal(localOCR.status, 'ok', 'The pinned local OCR worker and English model must initialize');
  assert.ok(localOCR.wordCount >= 5, 'Actual OCR must recognize the synthetic multi-cue menu');
  assert.equal(localOCR.context, 'lobby');
  assert.equal(localOCR.readerState.busy, false);
  assert.equal(localOCR.readerState.initialized, false, 'Terminating the reader must release its worker');
  report.localOCR = localOCR;
  report.steps.push('real-local-ocr-classifies-synthetic-lobby-and-releases-worker');
  const setupView = await readMapView();
  assert.equal(setupView.view, 'setup');
  assert.equal(setupView.main.visible, false, 'Before connection, the center must show setup rather than a blank/gameplay canvas');
  assert.equal(setupView.sourcePanelVisible, false);
  assert.equal(setupView.connect.visible, true, 'The main stage must offer the primary screen-connection action');
  assert.equal(setupView.connect.disabled, false, 'Connection must be available once the engine is ready');
  report.setupView = setupView;
  await page.screenshot({path: path.join(evidence, 'initial-connection.png'), fullPage: true});
  report.steps.push('initial-stage-shows-primary-connection-action-without-gameplay');

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
          context: 'map-only', ticket: {epoch: 1, sequence: index + 1}}));
      }
      return {ready, loaded, map: demo.map, results};
    } finally { worker.terminate(); }
  });
  assert.equal(workerResults.ready.version, '314.0.7');
  assert.equal(workerResults.loaded.count, 1);
  assert.equal(workerResults.results.length, 3);
  workerResults.results.forEach((result, index) => {
    assert.deepEqual(result.ticket, {epoch: 1, sequence: index + 1}, 'Object frame ticket must survive worker/Python boundaries exactly');
    assertMapOnlyState(result);
    assert.equal(result.timings.markerMs, 0);
    assert.equal(result.timings.zoneMs, 0);
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

  await page.evaluate(() => window.lootLizard.demo());
  await page.waitForFunction(() => window.lootLizard.getState().mapId === 'demo', null, {timeout: 60_000});
  assert.ok(await page.locator('#target-list tr').count() > 0);
  const demoView = await readMapView();
  assertCroppedMap(demoView);
  await page.screenshot({path: path.join(evidence, 'synthetic-demo.png'), fullPage: true});
  report.demoState = await page.evaluate(() => window.lootLizard.getState());
  assertMapOnlyState(report.demoState);
  assert.equal(await page.locator('.targets-table th').count(), 2);
  assert.equal(await page.locator('#target-list tr').first().locator('td').count(), 2);
  report.demoView = demoView;
  report.steps.push('test-only-demo-renders-real-map-registration-and-two-column-targets');

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
  assertStoppedView(await readMapView());
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
  assertStoppedView(await readMapView());
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
    const originalPost = Worker.prototype.postMessage;
    const fixture = {canvas, stream, frames: demo.frames, scans: [], analyzePosts: [], originalPost};
    window.__syntheticCapture = fixture;
    Worker.prototype.postMessage = function(message) {
      if (message?.type === 'analyze') fixture.analyzePosts.push({context: message.context, mapId: message.mapId ?? null});
      return Reflect.apply(originalPost, this, arguments);
    };
    const observer = new MutationObserver(() => {
      const state = window.lootLizard.getState();
      if (state.phase === 'scanning') window.__syntheticCapture.scans.push({...state,
        view: document.querySelector('#map-stage').dataset.view,
        mainVisible: !document.querySelector('#map-canvas').hidden,
        targetCount: document.querySelectorAll('#target-list tr').length});
    });
    observer.observe(document.querySelector('#recognition-status'), {childList: true, characterData: true, subtree: true});
    window.__syntheticCapture.observer = observer;
    await window.lootLizard.startTestStream(stream, {demo: true});
    window.__syntheticCapture.detailsOpenAtStart = document.querySelector('#source-details').open;
  });
  const otherTab = await context.newPage();
  await otherTab.goto('about:blank');
  await otherTab.bringToFront();
  await page.waitForFunction(() => {
    const state = window.lootLizard.getState();
    return state.sharing && state.phase === 'recognized' && state.mapId === 'demo' && state.points.length > 0;
  }, null, {timeout: 60_000});
  report.passiveStreamState = await page.evaluate(() => window.lootLizard.getState());
  assertMapOnlyState(report.passiveStreamState);
  assert.equal(await page.evaluate(() => window.__syntheticCapture.detailsOpenAtStart), true,
    'A newly connected stream must initially expand its preview before a map is found');
  const sharedMapView = await readMapView();
  assertCroppedMap(sharedMapView);
  assertCollapsedSource(sharedMapView);
  assert.equal(sharedMapView.reset.disabled, false);
  assert.equal(sharedMapView.retainedBannerVisible, false, 'A current recognized map needs no retained-map notice');
  report.sharedMapView = sharedMapView;
  report.steps.push('first-recognized-map-crops-bounds-and-collapses-preview-with-reset-still-visible');
  await page.bringToFront();
  await page.locator('#source-details > summary').click();
  assertSourcePreview(await readMapView());
  await otherTab.bringToFront();
  await page.evaluate(() => {
    const fixture = window.__syntheticCapture;
    fixture.scans.length = 0;
    fixture.gameplayStartedAt = performance.timeOrigin + performance.now();
    fixture.canvas.getContext('2d').putImageData(fixture.frames[1], 0, 0);
    fixture.stream.getVideoTracks()[0].requestFrame?.();
  });
  await page.waitForFunction(() => {
    const state = window.lootLizard.getState();
    return state.sharing && state.phase === 'unknown' && state.mapId === 'demo' && state.points.length > 0;
  }, null, {timeout: 60_000});
  const firstGameplay = await page.evaluate(() => ({state: window.lootLizard.getState(),
    completed: window.lootLizard.getPerformance().events.filter(event => event.type === 'scan' &&
      event.path === 'worker' && event.epochMs >= window.__syntheticCapture.gameplayStartedAt).length}));
  // A video element may deliver one last old map frame immediately after the
  // canvas changes. Compare two completed gameplay scans so a legitimate final
  // map frame cannot make the retained-age assertion depend on event timing.
  await page.waitForFunction(completed => {
    const fixture = window.__syntheticCapture, state = window.lootLizard.getState();
    const scans = window.lootLizard.getPerformance().events.filter(event => event.type === 'scan' &&
      event.path === 'worker' && event.epochMs >= fixture.gameplayStartedAt);
    return state.phase === 'unknown' && state.mapId === 'demo' && scans.length > completed;
  }, firstGameplay.completed, {timeout: 60_000});
  const gameplayUI = await page.evaluate(() => ({state: window.lootLizard.getState(), scans: window.__syntheticCapture.scans}));
  assert.ok(gameplayUI.scans.length > 0, 'Automatic stream must actually process the changed frame');
  assert.ok(gameplayUI.scans.every(state => state.mapId === 'demo' && state.points.length > 0 &&
    state.view === 'map' && state.mainVisible && state.targetCount > 0),
  'Scanning gameplay must retain the recognized map and its targets instead of replacing its bitmap');
  assert.equal(gameplayUI.state.mapUpdatedAt, firstGameplay.state.mapUpdatedAt,
    'Unrecognized gameplay must not refresh the age of the retained map');
  assert.equal(gameplayUI.state.positionUpdatedAt, report.passiveStreamState.positionUpdatedAt);
  assert.equal(gameplayUI.state.zoneUpdatedAt, report.passiveStreamState.zoneUpdatedAt);
  assert.deepEqual(gameplayUI.state.points, report.passiveStreamState.points);
  const registrationPosts = await page.evaluate(() => window.__syntheticCapture.analyzePosts);
  assert.equal(registrationPosts[0].mapId, null, 'The first map must be identified without a trusted-map hint');
  assert.ok(registrationPosts.some(post => post.mapId === 'demo'), 'Later scans must reuse the verified match map');
  assert.ok(registrationPosts.every(post => post.context === 'map-only'));
  assert.ok(await page.locator('#target-list tr').count() > 0);
  const gameplayView = await readMapView();
  assertCroppedMap(gameplayView);
  assert.equal(gameplayView.main.pixelHash, sharedMapView.main.pixelHash,
    'The retained central map pixels must stay paired with their old registration, never with the gameplay frame');
  assert.equal(gameplayView.retainedBannerVisible, true, 'A retained map must be labeled clearly');
  assertSourcePreview(gameplayView);
  assert.deepEqual(gameplayView.preview.centerPixel, [31, 42, 48, 255],
    'The small preview must update to the current gameplay frame rather than retaining the old map');
  report.gameplayView = gameplayView;
  await page.screenshot({path: path.join(evidence, 'retained-map-during-gameplay.png'), fullPage: true});
  report.steps.push('gameplay-updates-small-preview-while-recognized-map-and-ages-stay-paired');
  await page.evaluate(() => {
    const fixture = window.__syntheticCapture;
    fixture.canvas.getContext('2d').putImageData(fixture.frames[2], 0, 0);
    fixture.stream.getVideoTracks()[0].requestFrame?.();
  });
  await page.waitForFunction(previous => {
    const state = window.lootLizard.getState();
    return state.phase === 'recognized' && state.mapId === 'demo' && state.mapUpdatedAt > previous;
  }, gameplayUI.state.mapUpdatedAt, {timeout: 60_000});
  const returnedMapView = await readMapView();
  assertCroppedMap(returnedMapView);
  assertSourcePreview(returnedMapView);
  assert.equal(returnedMapView.retainedBannerVisible, false, 'A fresh recognized map must clear the retained notice');
  report.streamGameplay = gameplayUI;
  report.streamMapReturn = await page.evaluate(() => window.lootLizard.getState());
  report.steps.push('automatic-stream-map-gameplay-map-retains-guidance-until-fresh-map-arrives');

  // Reset is an explicit match boundary. It clears guidance while preserving
  // the already-approved source, even if the current image is ordinary play.
  await page.evaluate(() => {
    const fixture = window.__syntheticCapture;
    fixture.canvas.getContext('2d').putImageData(fixture.frames[1], 0, 0);
    fixture.stream.getVideoTracks()[0].requestFrame?.();
  });
  await page.waitForFunction(() => {
    const state = window.lootLizard.getState();
    return state.sharing && state.phase === 'unknown' && state.mapId === 'demo';
  }, null, {timeout: 60_000});
  await page.bringToFront();
  await page.locator('#source-details > summary').click();
  assertCollapsedSource(await readMapView());
  await page.evaluate(() => document.querySelector('#reset-match').addEventListener('click', () => {
    window.__syntheticCapture.resetPostIndex = window.__syntheticCapture.analyzePosts.length;
  }, {capture: true, once: true}));
  await page.locator('#reset-match').click();
  const reset = await page.evaluate(() => ({state: window.lootLizard.getState(),
    trackState: window.__syntheticCapture.stream.getVideoTracks()[0].readyState,
    sameStream: document.querySelector('#capture-video').srcObject === window.__syntheticCapture.stream}));
  assert.equal(reset.state.sharing, true, 'Reset match must keep the approved capture running');
  assert.equal(reset.trackState, 'live');
  assert.equal(reset.sameStream, true);
  assert.equal(reset.state.mapId, null);
  assert.deepEqual(reset.state.points, []);
  assert.equal(reset.state.position, null);
  assert.equal(reset.state.zone, null);
  assert.equal(reset.state.mapUpdatedAt, null);
  assert.equal(reset.state.positionUpdatedAt, null);
  assert.equal(reset.state.zoneUpdatedAt, null);
  assert.equal(await page.locator('#target-list tr').count(), 0);
  const resetView = await readMapView();
  assert.equal(resetView.main.visible, false);
  assert.equal(resetView.retainedBannerVisible, false);
  assertCollapsedSource(resetView);
  assert.equal(await page.locator('#reset-match').isDisabled(), true);
  report.resetMatch = {reset, view: resetView};
  await page.evaluate(() => {
    const fixture = window.__syntheticCapture;
    fixture.canvas.getContext('2d').putImageData(fixture.frames[2], 0, 0);
    fixture.stream.getVideoTracks()[0].requestFrame?.();
  });
  await page.waitForFunction(previous => {
    const state = window.lootLizard.getState();
    return state.sharing && state.phase === 'recognized' && state.mapId === 'demo' && state.mapUpdatedAt > previous;
  }, report.streamMapReturn.mapUpdatedAt, {timeout: 60_000});
  const reacquiredView = await readMapView();
  assertCroppedMap(reacquiredView);
  assertCollapsedSource(reacquiredView);
  const resetPosts = await page.evaluate(() => {
    const fixture = window.__syntheticCapture;
    return fixture.analyzePosts.slice(fixture.resetPostIndex);
  });
  assert.ok(resetPosts.length > 0);
  assert.equal(resetPosts[0].mapId, null, 'Reset must remove the previous trusted-map restriction before identifying the next map');
  report.afterResetState = await page.evaluate(() => window.lootLizard.getState());
  report.steps.push('manual-reset-clears-map-ages-without-ending-stream-and-next-map-reacquires');
  await page.evaluate(() => {
    const track = window.__syntheticCapture.stream.getVideoTracks()[0];
    track.stop();
    // MediaStreamTrack.stop() intentionally does not fire 'ended'. Dispatch the
    // event here to model the browser's user-driven Stop sharing notification.
    track.dispatchEvent(new Event('ended'));
    window.__syntheticCapture.observer.disconnect();
    Worker.prototype.postMessage = window.__syntheticCapture.originalPost;
  });
  await page.waitForFunction(() => !window.lootLizard.getState().sharing);
  const ended = await page.evaluate(() => window.lootLizard.getState());
  assert.equal(ended.mapId, null);
  assert.deepEqual(ended.points, []);
  assert.equal(ended.position, null);
  assert.equal(ended.zone, null);
  const endedView = await readMapView();
  assertStoppedView(endedView);
  assert.equal(await page.locator('#target-list tr').count(), 0);
  report.endedState = ended;
  report.endedView = endedView;
  report.steps.push('synthetic-stream-automatic-scan-and-ended-clears-state');

  await page.bringToFront();
  assert.equal((await readMapView()).sourceDetailsOpen, true, 'Stopping resets the disclosure for the next connection');
  await page.evaluate(async () => {
    const fixture = window.__syntheticCapture;
    fixture.stream = fixture.canvas.captureStream(2);
    // A restarted canvas stream needs a fresh paint. Repaint until video.play()
    // receives its first frame; an unchanged, previously stopped canvas may
    // otherwise never emit one in headless Chromium.
    const paint = () => {
      fixture.canvas.getContext('2d').putImageData(fixture.frames[0], 0, 0);
      fixture.stream.getVideoTracks()[0].requestFrame?.();
    };
    const repaint = setInterval(paint, 200);
    let timeout;
    try {
      const started = window.lootLizard.startTestStream(fixture.stream, {demo: true});
      paint();
      await Promise.race([started, new Promise((_, reject) => {
        timeout = setTimeout(() => reject(Error('Restarted synthetic stream produced no playable frame')), 30_000);
      })]);
      fixture.detailsOpenAtRestart = document.querySelector('#source-details').open;
    } finally { clearInterval(repaint); clearTimeout(timeout); }
  });
  await page.waitForFunction(() => window.lootLizard.getState().mapId === 'demo', null, {timeout: 60_000});
  assert.equal(await page.evaluate(() => window.__syntheticCapture.detailsOpenAtRestart), true);
  assertCollapsedSource(await readMapView());
  await page.evaluate(() => window.lootLizard.configureTestProcessing('capture-only'));
  const modeCleared = await page.evaluate(() => ({state: window.lootLizard.getState(),
    mode: window.lootLizard.getPerformance().mode}));
  assert.equal(modeCleared.mode, 'capture-only');
  assert.equal(modeCleared.state.sharing, true, 'Pausing processing must retain the approved capture stream');
  assert.equal(modeCleared.state.mapId, null);
  assert.deepEqual(modeCleared.state.points, []);
  assert.equal(modeCleared.state.position, null);
  assert.equal(modeCleared.state.zone, null);
  assert.equal(await page.locator('#target-list tr').count(), 0);
  const modeView = await readMapView();
  assert.equal(modeView.main.visible, false, 'Pausing recognition must remove the former map from the main stage');
  assert.notEqual(modeView.view, 'map');

  await page.evaluate(() => window.lootLizard.configureTestProcessing('full'));
  const inflightMode = await page.evaluate(async () => {
    const {createDemo} = await import('/app/demo.mjs');
    let scanningState;
    const switched = new Promise(resolve => {
      const observer = new MutationObserver(() => {
        if (window.lootLizard.getState().phase !== 'scanning') return;
        observer.disconnect();
        scanningState = window.lootLizard.getState();
        // As in the Stop test, queue the test-only processing change after the
        // already-enqueued worker post, before its reply can run as a task.
        queueMicrotask(() => {
          window.lootLizard.configureTestProcessing('capture-only');
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
  assert.equal((await readMapView()).main.visible, false, 'An invalidated late reply must not restore the main map canvas');
  report.modeCleared = modeCleared;
  report.inflightMode = inflightMode;
  report.steps.push('diagnostic-mode-clears-map-and-rejects-in-flight-worker-geometry');

  await page.evaluate(() => window.lootLizard.configureTestProcessing('full'));
  // Exercise the production match-context path: demo streams intentionally skip
  // OCR. Use the already-reviewed official reference, never a private capture.
  await page.evaluate(async () => {
    const {AUTOMATIC_REFERENCES, fetchReference} = await import('/app/automatic-references.mjs');
    const record = AUTOMATIC_REFERENCES.find(item => item.mapId === 'erangel');
    const bitmap = await createImageBitmap(await fetchReference(record));
    const canvas = document.createElement('canvas');
    canvas.width = 960; canvas.height = 720;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#111820'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(bitmap, 160, 40, 640, 640); bitmap.close();
    const mapFrame = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const stream = canvas.captureStream(2);
    window.__contextCapture = {canvas, stream, mapFrame};
    const paint = () => {ctx.putImageData(mapFrame, 0, 0); stream.getVideoTracks()[0].requestFrame?.();};
    const repaint = setInterval(paint, 200);
    let timeout;
    try {
      const started = window.lootLizard.startTestStream(stream, {demo: false});
      paint();
      await Promise.race([started, new Promise((_, reject) => {
        timeout = setTimeout(() => reject(Error('Official-reference synthetic stream produced no playable frame')), 30_000);
      })]);
    } finally {clearInterval(repaint); clearTimeout(timeout);}
  });
  await page.waitForFunction(() => {
    const state = window.lootLizard.getState();
    return state.sharing && state.phase === 'recognized' && state.mapId === 'erangel';
  }, null, {timeout: 120_000});
  const officialMapState = await page.evaluate(() => window.lootLizard.getState());
  const officialMapView = await readMapView();
  assertCroppedMap(officialMapView);
  assertCollapsedSource(officialMapView);
  assertMapOnlyState(officialMapState);
  await page.locator('#source-details > summary').click();
  assertSourcePreview(await readMapView());
  await page.evaluate(() => {
    const fixture = window.__contextCapture, ctx = fixture.canvas.getContext('2d');
    fixture.unknownStartedAt = Date.now();
    ctx.fillStyle = '#29363d'; ctx.fillRect(0, 0, fixture.canvas.width, fixture.canvas.height);
    fixture.stream.getVideoTracks()[0].requestFrame?.();
  });
  await page.waitForFunction(() => {
    const fixture = window.__contextCapture, state = window.lootLizard.getState();
    const unknownScans = window.lootLizard.getPerformance().events.filter(event =>
      event.type === 'scan' && event.path === 'worker' && event.epochMs >= fixture.unknownStartedAt);
    return state.sharing && state.phase === 'unknown' && state.mapId === 'erangel' && unknownScans.length >= 1;
  }, null, {timeout: 60_000});
  const firstUnknownContext = await page.evaluate(() => ({state: window.lootLizard.getState(),
    completed: window.lootLizard.getPerformance().events.filter(event => event.type === 'scan' &&
      event.path === 'worker' && event.epochMs >= window.__contextCapture.unknownStartedAt).length}));
  await page.waitForFunction(completed => {
    const fixture = window.__contextCapture, state = window.lootLizard.getState();
    const unknownScans = window.lootLizard.getPerformance().events.filter(event =>
      event.type === 'scan' && event.path === 'worker' && event.epochMs >= fixture.unknownStartedAt);
    return state.sharing && state.phase === 'unknown' && state.mapId === 'erangel' && unknownScans.length > completed;
  }, firstUnknownContext.completed, {timeout: 60_000});
  const unknownContextState = await page.evaluate(() => window.lootLizard.getState());
  assert.equal(unknownContextState.mapUpdatedAt, firstUnknownContext.state.mapUpdatedAt,
    'Missing map/footer pixels alone must not age-reset or discard the retained match');
  const unknownContextView = await readMapView();
  assertCroppedMap(unknownContextView);
  assert.equal(unknownContextView.main.pixelHash, officialMapView.main.pixelHash);
  assert.equal(unknownContextView.retainedBannerVisible, true);
  await page.evaluate(() => {
    const fixture = window.__contextCapture, ctx = fixture.canvas.getContext('2d');
    fixture.lobbyStartedAt = Date.now();
    ctx.fillStyle = '#111820'; ctx.fillRect(0, 0, fixture.canvas.width, fixture.canvas.height);
    ctx.fillStyle = '#ffffff'; ctx.font = 'bold 32px Arial';
    ctx.fillText('PLAY    CAREER    CUSTOMIZE    WORKSHOP    STORE', 32, 64);
    ctx.fillText('NORMAL', 32, fixture.canvas.height * .7);
    ctx.fillText('PLAY', 32, fixture.canvas.height * .9);
    fixture.stream.getVideoTracks()[0].requestFrame?.();
  });
  await page.waitForFunction(() => {
    const state = window.lootLizard.getState();
    return state.sharing && state.mapId === null && state.mapUpdatedAt === null;
  }, null, {timeout: 120_000});
  const automaticContextReset = await page.evaluate(() => {
    const fixture = window.__contextCapture;
    return {state: window.lootLizard.getState(),
      sameStream: document.querySelector('#capture-video').srcObject === fixture.stream,
      trackState: fixture.stream.getVideoTracks()[0].readyState,
      contextEvents: window.lootLizard.getPerformance().events.filter(event =>
        event.type === 'match-context' && event.epochMs >= fixture.lobbyStartedAt)};
  });
  assert.equal(automaticContextReset.sameStream, true);
  assert.equal(automaticContextReset.trackState, 'live');
  assert.equal(automaticContextReset.state.sharing, true);
  assert.deepEqual(automaticContextReset.state.points, []);
  assert.equal(automaticContextReset.state.position, null);
  assert.equal(automaticContextReset.state.zone, null);
  assert.ok(automaticContextReset.contextEvents.filter(event => event.status === 'ok' && event.context === 'lobby').length >= 3,
    'Actual OCR must provide a positive lobby quorum before automatic reset');
  const automaticResetView = await readMapView();
  assert.equal(automaticResetView.main.visible, false);
  assert.equal(automaticResetView.retainedBannerVisible, false);
  assertSourcePreview(automaticResetView);
  report.automaticContextReset = {officialMapState, unknownContextState, ...automaticContextReset};
  report.steps.push('real-ocr-lobby-quorum-clears-retained-official-map-without-stopping-stream');
  await page.evaluate(() => {window.lootLizard.stop(); delete window.__contextCapture;});

  await page.evaluate(() => window.lootLizard.demo());
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
  const noReferenceView = await readMapView();
  assert.equal(noReferenceView.main.visible, false, 'Missing references must not promote a source screenshot into the map stage');
  assert.notEqual(noReferenceView.view, 'map');
  assertSourcePreview(noReferenceView);
  await page.evaluate(() => {
    window.lootLizard.stop();
    Worker.prototype.postMessage = window.__noReferenceCapture.originalPost;
    delete window.__noReferenceCapture;
  });
  assertStoppedView(await readMapView());
  report.noReferences = noReferences;
  report.noReferenceView = noReferenceView;
  report.steps.push('empty-reference-screen-fast-path-samples-without-worker-transfer-or-stale-geometry');
  assert.ok(report.requests.every(request => ['GET', 'HEAD'].includes(request.method)), 'No image upload request may be issued');
  assert.ok(report.requests.some(request => new URL(request.url).pathname === '/data/maps.json'), 'Map metadata must come from the bundled release catalog');
  assert.ok(report.requests.every(request => !/\/metadata\/maps\.json(?:\?|$)/.test(new URL(request.url).pathname)), 'Running clients must not poll a GitHub metadata branch');
  assert.ok(report.requests.every(request => {
    const url = new URL(request.url);
    return !/\.png$/i.test(url.pathname) || url.hostname === '127.0.0.1';
  }), 'Official reference PNGs must come from the bundled origin, never a map CDN');
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
