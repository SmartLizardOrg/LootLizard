import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {applyLanguage, translate} from '../app/i18n.mjs';

const html = readFileSync(new URL('../app/index.html', import.meta.url), 'utf8');
const controller = readFileSync(new URL('../app/app.js', import.meta.url), 'utf8');
const staticKeys = [...new Set([...html.matchAll(/data-i18n="([^"]+)"/g)].map(match => match[1]))];
const accessibleKeys = [...new Set([...html.matchAll(/data-i18n-aria-label="([^"]+)"/g)].map(match => match[1]))];

test('all player labels and accessible names have Hungarian translations', () => {
  assert.ok(staticKeys.length > 25);
  assert.ok(accessibleKeys.length >= 6);
  for (const key of [...staticKeys, ...accessibleKeys]) {
    assert.equal(translate(key, 'en'), key);
    assert.notEqual(translate(key, 'hu'), key, `Missing Hungarian message: ${key}`);
    assert.ok(translate(key, 'hu').trim());
  }
});

test('player-facing controller phases, instructions and failures have Hungarian coverage', () => {
  const literals = [...controller.matchAll(/\bt\('([^']+)'\)/g)].map(match => match[1]);
  const phases = controller.match(/const names=\{([^}]+)\}/)?.[1] || '';
  const phaseKeys = [...phases.matchAll(/:'([^']+)'/g)].map(match => match[1]);
  const messages = controller.match(/const messages=\{([\s\S]*?)\n\s*\};/)?.[1] || '';
  const instructionKeys = [...messages.matchAll(/'([^']+)'/g)].map(match => match[1]);
  const statusKeys = [...controller.matchAll(/\bstatus\(\s*'[^']+'\s*,\s*'([^']+)'/g)].map(match => match[1]);
  const fallbackKeys = [...controller.matchAll(/detail\|\|'([^']+)'/g)].map(match => match[1]);
  const mapResult = controller.match(/,result\.registration\?'([^']+)':'([^']+)'/);
  const branchKeys = [
    'Connected', 'Not sharing', 'Sharing is paused.', 'Your connected PUBG source', 'Waiting for your game…',
    'Map saved', 'Your map stays here while you play. Open it in game to refresh.',
    'Connect PUBG, then open the full map in game.',
    'Waiting for a new match', 'Ready for your next match. Open the map in game.',
    'No locations listed for this map yet.', 'Locations appear here when your map is recognized.',
    'Map images are unavailable. Refresh this page to try again.',
  ];
  assert.ok(phaseKeys.length >= 7, 'Expected the player-facing recognition lifecycle');
  assert.ok(instructionKeys.length >= 7, 'Expected setup, connecting, waiting and error instructions');
  assert.ok(mapResult, 'Expected recognized/unknown map guidance');
  for (const key of branchKeys) assert.ok(controller.includes("'" + key + "'"), `Stale branch coverage: ${key}`);
  const keys = new Set([...literals, ...phaseKeys, ...instructionKeys, ...statusKeys, ...fallbackKeys, ...mapResult.slice(1), ...branchKeys]);
  for (const key of keys) assert.notEqual(translate(key, 'hu'), key, `Missing Hungarian status: ${key}`);
});

test('unknown messages and English preserve the original value safely', () => {
  for (const key of ['Future message', 'constructor', '__proto__', '{count} locations']) {
    assert.equal(translate(key, 'hu'), key);
    assert.equal(translate(key, 'en'), key);
    assert.equal(translate(key, 'invalid'), key);
  }
  assert.equal(translate('Connect PUBG window'), 'Connect PUBG window');
});

test('language changes preserve selected interval, disclosure state and action handlers', () => {
  const nodes = staticKeys.map(key => ({textContent: key, getAttribute: () => key}));
  const accessibleNodes = accessibleKeys.map(key => ({
    label: key, getAttribute: () => key,
    setAttribute(name, value) { assert.equal(name, 'aria-label'); this.label = value; },
  }));
  const onChange = () => {};
  const setup = {language: {value: 'hu'}, interval: {value: '5000', onchange: onChange}, sourceDetails: {open: false}};
  const previous = globalThis.document;
  globalThis.document = {
    documentElement: {lang: 'en'},
    querySelectorAll: selector => {
      if (selector === '[data-i18n]') return nodes;
      if (selector === '[data-i18n-aria-label]') return accessibleNodes;
      assert.fail(`Unexpected selector: ${selector}`);
    },
  };
  try {
    assert.equal(applyLanguage('hu'), 'hu');
    assert.equal(document.documentElement.lang, 'hu');
    nodes.forEach((node, index) => assert.equal(node.textContent, translate(staticKeys[index], 'hu')));
    accessibleNodes.forEach((node, index) => assert.equal(node.label, translate(accessibleKeys[index], 'hu')));
    assert.equal(applyLanguage('en'), 'en');
    nodes.forEach((node, index) => assert.equal(node.textContent, staticKeys[index]));
    accessibleNodes.forEach((node, index) => assert.equal(node.label, accessibleKeys[index]));
    assert.equal(applyLanguage('invalid'), 'en');
    assert.equal(document.documentElement.lang, 'en');
    assert.equal(setup.language.value, 'hu');
    assert.equal(setup.interval.value, '5000');
    assert.equal(setup.interval.onchange, onChange);
    assert.equal(setup.sourceDetails.open, false);
  } finally {
    if (previous === undefined) delete globalThis.document;
    else globalThis.document = previous;
  }
});

test('settings offer only language and the requested refresh intervals, defaulting to one second', () => {
  const selects = [...html.matchAll(/<select\b[^>]*id="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)];
  assert.deepEqual(selects.map(match => match[1]).sort(), ['language-select', 'scan-interval']);
  const options = [...selects.find(match => match[1] === 'scan-interval')[2].matchAll(/<option\b([^>]*)>/g)].map(match => match[1]);
  assert.deepEqual(options.map(value => Number(value.match(/value="(\d+)"/)[1])), [500, 1000, 2000, 5000, 10000]);
  assert.deepEqual(options.filter(value => /\bselected\b/.test(value)).map(value => Number(value.match(/value="(\d+)"/)[1])), [1000]);
  assert.match(html, /<html lang="en">/);
  assert.doesNotMatch(html, /<input\b/);
});

test('source preview is optional while reset remains outside its disclosure', () => {
  const source = html.match(/<section id="source-panel"([\s\S]*?)<\/section>/)?.[1];
  assert.ok(source);
  const disclosure = source.match(/<details id="source-details"([\s\S]*?)<\/details>/);
  assert.ok(disclosure);
  assert.match(disclosure[1], /id="source-preview"/);
  assert.match(disclosure[1], /id="source-status"/);
  assert.doesNotMatch(disclosure[1], /id="reset-match"/);
  assert.match(source.slice(source.indexOf('</details>')), /id="reset-match"/);
  assert.match(source, /id="source-preview" width="240" height="135"/);
});

test('map navigation is initially hidden and gives pointer and keyboard guidance', () => {
  const canvas = html.match(/<canvas id="map-canvas"[^>]*>/)?.[0] || '';
  assert.match(canvas, /tabindex="0"/);
  assert.match(canvas, /aria-describedby="map-navigation-hint map-keyboard-hint"/);
  const navigation = html.match(/<div id="map-navigation"([^>]+)>/)[1];
  assert.match(navigation, /\bhidden\b/);
  assert.match(navigation, /role="group"/);
  assert.match(navigation, /data-i18n-aria-label="Map navigation"/);
  for (const [id, label] of [['map-zoom-out', 'Zoom out'], ['map-zoom-in', 'Zoom in']]) {
    const control = html.match(new RegExp(`<button id="${id}"[^>]*>`))?.[0] || '';
    assert.match(control, /type="button"/);
    assert.ok(control.includes(`data-i18n-aria-label="${label}"`));
  }
  assert.match(html, /<button id="map-fit"[^>]*data-i18n="Fit map">Fit map<\/button>/);
  assert.match(html, /<output id="map-zoom-level"[^>]*aria-live="off">100%<\/output>/);
  assert.match(html, /id="map-navigation-hint"[^>]*data-i18n="Scroll to zoom · drag to move"/);
  assert.match(html, /id="map-keyboard-hint"[^>]*class="visually-hidden"/);
});

test('location list contains only rank and location, with no developer or identity controls', () => {
  const headings = html.match(/<thead>([\s\S]*?)<\/thead>/)?.[1] || '';
  assert.equal([...headings.matchAll(/<th\b/g)].length, 2);
  assert.match(headings, /data-i18n="Rank"/);
  assert.match(headings, /data-i18n="Location"/);
  for (const removed of ['load-demo', 'open-image', 'engine-status', 'inside-count', 'position-status', 'circle-status',
    'scan-duration', 'reference-map', 'reference-file', 'crop-reference', 'metadata-status', 'performance-diagnostics',
    'capture-rate', 'capture-work', 'export-performance', 'replay-mode', 'cache-preferences']) {
    assert.equal(html.includes('id="' + removed + '"'), false, `Removed player control remains: ${removed}`);
  }
  assert.doesNotMatch(html, /OpenCV|Pyodide|identity|distance|inside circle|local performance diagnostics/i);
});
