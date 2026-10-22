import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {applyLanguage, translate} from '../app/i18n.mjs';

const html = readFileSync(new URL('../app/index.html', import.meta.url), 'utf8');
const controller = readFileSync(new URL('../app/app.js', import.meta.url), 'utf8');
const staticKeys = [...new Set([...html.matchAll(/data-i18n="([^"]+)"/g)].map(match => match[1]))];

test('every current static UI message has a nonempty Hungarian translation', () => {
  assert.ok(staticKeys.length > 40);
  for (const key of staticKeys) {
    assert.equal(translate(key, 'en'), key);
    assert.notEqual(translate(key, 'hu'), key, `Missing Hungarian message: ${key}`);
    assert.ok(translate(key, 'hu').trim());
  }
});

test('controller translation calls and recognition phases have Hungarian coverage', () => {
  const literals = [...controller.matchAll(/\bt\('([^']+)'\)/g)].map(match => match[1]);
  const phases = controller.match(/const names=\{([^}]+)\}/)?.[1] || '';
  const phaseKeys = [...phases.matchAll(/:'([^']+)'/g)].map(match => match[1]);
  const statusKeys = [...controller.matchAll(/\bstatus\(\s*'[^']+'\s*,\s*'([^']+)'/g)].map(match => match[1]);
  const metadataKeys = [...controller.matchAll(/\bmetadataKey\s*=\s*'([^']+)'/g)].map(match => match[1]);
  const detailKeys = [...controller.matchAll(/\bdetail\s*=\s*'([^']+)'/g)].map(match => match[1]);
  const fallbackKeys = [...controller.matchAll(/detail\|\|'([^']+)'/g)].map(match => match[1]);
  const recognizedKeys = [...controller.matchAll(/result\.registration\?'([^']+)':result\.reason/g)].map(match => match[1]);
  assert.ok(phaseKeys.length >= 8);
  const branchKeys = [
    'Sharing screen', 'Synthetic demo', 'Local image', 'Not sharing',
    'Position estimate · identity unverified', 'Position unknown · distances unavailable',
    'Inside', 'Outside',
  ];
  const keys = new Set([...literals, ...phaseKeys, ...branchKeys, ...statusKeys, ...metadataKeys, ...detailKeys, ...fallbackKeys, ...recognizedKeys]);
  assert.ok(keys.size >= 30, 'Expected literal, deferred-status, phase and branch messages');
  assert.ok(keys.has('Small anchors mark exact coordinates. Distances are straight-line estimates.'));
  assert.ok(keys.has('Using saved coordinates'));
  assert.ok(keys.has('Recognition engine timed out. Reload this page.'));
  for (const key of keys) {
    assert.notEqual(translate(key, 'hu'), key, `Missing Hungarian status: ${key}`);
  }
});

test('unknown messages and English preserve the original value safely', () => {
  for (const key of ['Future worker message', 'constructor', '__proto__', '{count} rooms']) {
    assert.equal(translate(key, 'hu'), key);
    assert.equal(translate(key, 'en'), key);
    assert.equal(translate(key, 'invalid'), key);
  }
  assert.equal(translate('Start sharing'), 'Start sharing');
});

test('language changes translate labels without changing setup values or event handlers', () => {
  const nodes = staticKeys.map(key => ({textContent: key, getAttribute: () => key}));
  const setup = {
    language: {value: 'hu'}, interval: {value: '5000'}, map: {value: 'taego'},
    cache: {checked: false}, replay: {checked: true}, file: {value: 'private-reference.png'},
  };
  const onChange = () => {};
  setup.interval.onchange = onChange;
  const before = structuredClone({...setup, interval: {value: setup.interval.value}});
  const previous = globalThis.document;
  globalThis.document = {
    documentElement: {lang: 'en'},
    querySelectorAll: selector => {
      assert.equal(selector, '[data-i18n]');
      return nodes;
    },
  };
  try {
    assert.equal(applyLanguage('hu'), 'hu');
    assert.equal(document.documentElement.lang, 'hu');
    nodes.forEach((node, index) => assert.equal(node.textContent, translate(staticKeys[index], 'hu')));
    assert.equal(applyLanguage('en'), 'en');
    nodes.forEach((node, index) => assert.equal(node.textContent, staticKeys[index]));
    assert.equal(applyLanguage('invalid'), 'en');
    assert.equal(document.documentElement.lang, 'en');
    assert.deepEqual({...setup, interval: {value: setup.interval.value}}, before);
    assert.equal(setup.interval.onchange, onChange);
  } finally {
    if (previous === undefined) delete globalThis.document;
    else globalThis.document = previous;
  }
});
