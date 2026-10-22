import test from 'node:test';
import assert from 'node:assert/strict';
import {classifyMatchContext, NonMatchGate, createFooterDescriptor, matchFooterDescriptor} from '../app/match-context.mjs';

const word = (text, x, y, confidence = 95) => ({text, confidence,
  bbox: {x0: x * 1000, y0: y * 1000, x1: x * 1000 + 30, y1: y * 1000 + 20}});
const observation = words => ({words, width: 1000, height: 1000});
const lobby = () => observation([
  word('PLAY', .06, .04), word('CAREER', .20, .04), word('CUSTOMIZE', .35, .04),
  word('NORMAL', .07, .67), word('PLAY', .06, .90),
]);
const results = () => observation([
  word('BETTER LUCK NEXT TIME!', .1, .15), word('TEAM RANK', .1, .25), word('#8', .3, .25),
  word('RETURN TO LOBBY', .7, .90),
]);

test('lobby requires top navigation, lower queue action, and a left-side match mode', () => {
  const data = lobby();
  assert.equal(classifyMatchContext(data).context, 'lobby');
  for (const remove of [0, 3, 4]) {
    assert.equal(classifyMatchContext({...data, words: data.words.filter((_, index) => index !== remove)}).context, 'unknown');
  }
  assert.equal(classifyMatchContext(observation(data.words.map(item => ({...item,
    bbox: {...item.bbox, y0: item.bbox.y0 + (item.bbox.y0 < 100 ? 200 : 0), y1: item.bbox.y1 + (item.bbox.y0 < 100 ? 200 : 0)}})))).context, 'unknown');
});

test('results require an upper final-result headline, summary, and lower exit action', () => {
  const data = results();
  assert.equal(classifyMatchContext(data).context, 'results');
  for (const remove of [0, 1, 3]) {
    assert.equal(classifyMatchContext({...data, words: data.words.filter((_, index) => index !== remove)}).context, 'unknown');
  }
  const winner = results(); winner.words[0].text = 'WINNER WINNER CHICKEN DINNER!'; winner.words[3].text = 'CONTINUE';
  assert.equal(classifyMatchContext(winner).context, 'results');
});

test('pause return-to-lobby, inventory, ordinary gameplay, and common alt-tab text abstain', () => {
  for (const words of [
    [word('RESUME', .4, .3), word('SETTINGS', .4, .4), word('RETURN TO LOBBY', .4, .8)],
    [word('INVENTORY', .05, .1), word('VICINITY', .05, .2), word('M416', .8, .2)],
    [word('PHASE 4', .8, .8), word('12 ALIVE', .8, .05)],
    [word('PUBG BATTLEGROUNDS', .2, .1), word('STORE', .05, .04), word('LIBRARY', .2, .04), word('PLAY', .06, .9)],
    [word('RETURN TO LOBBY', .3, .9)],
  ]) assert.equal(classifyMatchContext(observation(words)).context, 'unknown');
  for (const token of ['RESUME', 'INVENTORY', 'SYSTEM MENU']) {
    const data = results(); data.words.push(word(token, .4, .4));
    assert.equal(classifyMatchContext(data).context, 'unknown');
  }
});

test('weak, invalid, or unpositioned OCR cannot authorize resetting a map', () => {
  assert.equal(classifyMatchContext({...lobby(), words: lobby().words.map(item => ({...item, confidence: 60}))}).context, 'unknown');
  assert.equal(classifyMatchContext({...lobby(), words: lobby().words.map(item => ({...item, bbox: undefined}))}).context, 'unknown');
  assert.equal(classifyMatchContext(observation([null, {}, undefined])).context, 'unknown');
  for (const data of [null, {}, {...lobby(), width: 0}, {...lobby(), words: new Array(1001).fill(word('PLAY', .1, .1))}]) {
    assert.equal(classifyMatchContext(data).context, 'unknown');
  }
});

test('three distinct consistent positive observations over time authorize one reset', () => {
  const gate = new NonMatchGate();
  assert.equal(gate.observe(lobby(), 0).shouldClear, false);
  assert.equal(gate.observe(lobby(), 3000).shouldClear, false);
  const confirmed = gate.observe(lobby(), 6000);
  assert.equal(confirmed.shouldClear, true);
  assert.equal(confirmed.confirmed, true);
  assert.equal(gate.observe(lobby(), 9000).shouldClear, false);
});

test('missing-map time and long unknown gameplay never clear retained maps', () => {
  const gate = new NonMatchGate();
  for (let now = 0; now <= 600000; now += 3000) {
    assert.equal(gate.observe(observation([]), now).shouldClear, false);
  }
});

test('unknown screens, registered maps, changed context, and long gaps break confirmation', () => {
  for (const interrupt of [observation([]), {registeredMap: true}, results()]) {
    const gate = new NonMatchGate();
    gate.observe(lobby(), 0); gate.observe(lobby(), 3000);
    assert.equal(gate.observe(interrupt, 6000).shouldClear, false);
    assert.equal(gate.observe(lobby(), 9000).shouldClear, false);
    assert.equal(gate.observe(lobby(), 12000).shouldClear, false);
    assert.equal(gate.observe(lobby(), 15000).shouldClear, true);
  }
  const gate = new NonMatchGate();
  gate.observe(lobby(), 0); gate.observe(lobby(), 3000);
  assert.equal(gate.observe(lobby(), 60000).shouldClear, false);
});

test('duplicate timestamps and backwards clocks cannot accelerate confirmation', () => {
  const gate = new NonMatchGate();
  gate.observe(lobby(), 0);
  assert.equal(gate.observe(lobby(), 0).count, 1);
  gate.observe(lobby(), 3000);
  assert.equal(gate.observe(lobby(), 1000).count, 1);
  assert.equal(gate.observe(lobby(), 7000).shouldClear, false);
  assert.equal(gate.observe(lobby(), 8000).shouldClear, true);
  assert.equal(gate.observe(lobby(), NaN).confirmed, false);
});

function footerFrame({background = 20, footer = true, changedSuffix = false, changedPrefix = false, width = 640, height = 360} = {}) {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < data.length; i += 4) {data[i] = background; data[i + 1] = background; data[i + 2] = background; data[i + 3] = 255;}
  if (footer) for (let glyph = 0; glyph < 28; glyph++) for (let y = 0; y < 7; y++) for (let x = 0; x < 3; x++) {
    // Deterministic synthetic text strokes; no game screenshot/identity fixture.
    const changed = (changedSuffix && glyph >= 20) || (changedPrefix && glyph < 12);
    const ink = changed ? (x + y + glyph) % 4 === 0 : x === 0 || y === 0 || (y + glyph) % 3 === x;
    if (!ink) continue;
    const at = ((height - 9 + y) * width + width - 112 + glyph * 4 + x) * 4;
    data[at] = data[at + 1] = data[at + 2] = 220;
  }
  return {data, width, height};
}

test('footer learning requires verified map context and rejects blank or unsuitable images', () => {
  assert.equal(createFooterDescriptor(footerFrame()), null);
  assert.equal(createFooterDescriptor(footerFrame({footer: false}), {verifiedMap: true}), null);
  assert.equal(createFooterDescriptor({width: 640, height: 360, data: new Uint8Array(4)}, {verifiedMap: true}), null);
  assert.ok(createFooterDescriptor(footerFrame(), {verifiedMap: true}));
});

test('in-memory footer evidence ignores dynamic suffixes but changed stable prefixes abstain', () => {
  const descriptor = createFooterDescriptor(footerFrame(), {verifiedMap: true});
  assert.equal(matchFooterDescriptor(footerFrame(), descriptor).present, true);
  assert.equal(matchFooterDescriptor(footerFrame({background: 75}), descriptor).present, true);
  assert.equal(matchFooterDescriptor(footerFrame({changedSuffix: true}), descriptor).present, true);
  for (const frame of [footerFrame({footer: false}), footerFrame({changedPrefix: true}), footerFrame({width: 800})]) {
    assert.equal(matchFooterDescriptor(frame, descriptor).present, false);
  }
  assert.equal(typeof descriptor.mask, 'object');
  assert.equal('text' in descriptor, false);
});

test('positive learned footer vetoes OCR reset while missing footer alone never resets', () => {
  const gate = new NonMatchGate();
  gate.observe(lobby(), 0); gate.observe(lobby(), 3000);
  const veto = gate.observe({...lobby(), footerPresent: true}, 6000);
  assert.equal(veto.context, 'match');
  assert.equal(veto.shouldClear, false);
  assert.equal(gate.observe({...observation([]), footerPresent: false}, 60000).shouldClear, false);
  assert.equal(gate.observe({...lobby(), footerPresent: false}, 63000).shouldClear, false);
});
