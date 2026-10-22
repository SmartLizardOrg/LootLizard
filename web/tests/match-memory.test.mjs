import test from 'node:test';
import assert from 'node:assert/strict';
import {MatchMapMemory} from '../app/match-memory.mjs';

const firstMatrix = [[640, 0, 160], [0, 640, 40], [0, 0, 1]];
const movedMatrix = [[320, 0, 30], [0, 320, 70], [0, 0, 1]];
const marker = () => ({x: .25, y: .5, screenCenter: [320, 360], identityVerified: false});
const circle = () => ({centerX: .5, centerY: .45, radius: .2, score: .9});
const recognized = (overrides = {}) => ({
  registration: {mapId: 'erangel', matrix: firstMatrix},
  position: marker(), zone: circle(), points: [{id: 'room', imageX: 400, imageY: 400}],
  ...overrides,
});
const frame = label => ({label, width: 960, height: 720, data: new Uint8ClampedArray(4)});

test('unregistered frames do not create memory', () => {
  const memory = new MatchMapMemory();
  assert.equal(memory.current, null);
  assert.equal(memory.update({registration: null, points: []}, frame('gameplay'), 10), false);
  assert.equal(memory.snapshot(), null);
});

test('registered map keeps its exact frame reference and independent timestamps', () => {
  const memory = new MatchMapMemory(), source = frame('map'), input = recognized();
  assert.equal(memory.update(input, source, 100), true);
  const current = memory.snapshot();
  assert.equal(current, memory.current);
  assert.equal(current.frame, source);
  assert.equal(current.frame.data, source.data);
  assert.deepEqual(current.result, input);
  assert.equal(current.mapUpdatedAt, 100);
  assert.equal(current.positionUpdatedAt, 100);
  assert.equal(current.zoneUpdatedAt, 100);
});

test('unknown gameplay or inventory retains the identical paired snapshot and ages', () => {
  const memory = new MatchMapMemory();
  memory.update(recognized(), frame('map'), 100);
  const before = memory.current;
  for (const reason of ['gameplay', 'inventory', 'unreadable']) {
    assert.equal(memory.update({registration: null, position: null, zone: null, points: [], reason}, frame(reason), 500), false);
    assert.equal(memory.current, before);
    assert.equal(memory.current.result, before.result);
    assert.equal(memory.current.frame, before.frame);
  }
  assert.equal(memory.current.mapUpdatedAt, 100);
});

test('a fresh registered frame replaces the frame, result and detected-field ages', () => {
  const memory = new MatchMapMemory();
  memory.update(recognized(), frame('old'), 100);
  const old = memory.current;
  const next = recognized({position: {...marker(), x: .7}, zone: {...circle(), radius: .1}});
  const source = frame('new');
  memory.update(next, source, 300);
  assert.notEqual(memory.current, old);
  assert.equal(memory.current.frame, source);
  assert.deepEqual(memory.current.result, next);
  assert.deepEqual([memory.current.mapUpdatedAt, memory.current.positionUpdatedAt, memory.current.zoneUpdatedAt], [300, 300, 300]);
});

test('missing position keeps world coordinates and age but uses the new registration', () => {
  const memory = new MatchMapMemory(), input = recognized();
  memory.update(input, frame('first'), 100);
  const points = [{id: 'new-room', imageX: 70, imageY: 90}];
  const next = recognized({registration: {mapId: 'erangel', matrix: movedMatrix}, position: null, points});
  memory.update(next, frame('zoomed'), 400);
  assert.deepEqual(memory.current.result.position, {...marker(), screenCenter: [110, 230]});
  assert.deepEqual(input.position.screenCenter, [320, 360]);
  assert.equal(next.position, null);
  assert.equal(memory.current.result.points, points);
  assert.equal(memory.current.mapUpdatedAt, 400);
  assert.equal(memory.current.positionUpdatedAt, 100);
  assert.equal(memory.current.zoneUpdatedAt, 400);
});

test('missing circle keeps its world geometry and original timestamp independently', () => {
  const memory = new MatchMapMemory();
  memory.update(recognized(), frame('first'), 100);
  const previousZone = memory.current.result.zone;
  memory.update(recognized({zone: null}), frame('second'), 250);
  assert.equal(memory.current.result.zone, previousZone);
  assert.equal(memory.current.zoneUpdatedAt, 100);
  assert.equal(memory.current.positionUpdatedAt, 250);
  assert.equal(memory.current.mapUpdatedAt, 250);
});

test('repeated missing fields preserve original ages and never reuse old screen coordinates', () => {
  const memory = new MatchMapMemory();
  memory.update(recognized(), frame('first'), 100);
  memory.update(recognized({registration: {mapId: 'erangel', matrix: movedMatrix}, position: null, zone: null}), frame('second'), 300);
  memory.update(recognized({registration: {mapId: 'erangel', matrix: [[0, -200, 200], [200, 0, 30], [0, 0, 1]]}, position: null, zone: null}), frame('third'), 600);
  assert.deepEqual(memory.current.result.position.screenCenter, [100, 80]);
  assert.equal(memory.current.positionUpdatedAt, 100);
  assert.equal(memory.current.zoneUpdatedAt, 100);
  assert.equal(memory.current.mapUpdatedAt, 600);
});

test('retained position drops screen coordinates when projection is unavailable', () => {
  for (const matrix of [null, [[1]], [[1, 0, 0], [0, 1, 0], [0, 0, 0]]]) {
    const memory = new MatchMapMemory();
    memory.update(recognized(), frame('first'), 100);
    assert.equal(memory.update(recognized({registration: {mapId: 'erangel', matrix}, position: null}), frame('second'), 200), true);
    assert.equal(memory.current.result.position.screenCenter, null);
    assert.equal(memory.current.result.position.x, .25);
    assert.equal(memory.current.positionUpdatedAt, 100);
  }
});

test('a different map clears absent position/circle instead of inheriting them', () => {
  const memory = new MatchMapMemory();
  memory.update(recognized(), frame('erangel'), 100);
  const input = recognized({registration: {mapId: 'taego', matrix: firstMatrix}, position: null, zone: null});
  memory.update(input, frame('taego'), 200);
  assert.equal(memory.current.result.registration.mapId, 'taego');
  assert.equal(memory.current.result.position, null);
  assert.equal(memory.current.result.zone, null);
  assert.equal(memory.current.positionUpdatedAt, null);
  assert.equal(memory.current.zoneUpdatedAt, null);
  assert.equal(memory.current.mapUpdatedAt, 200);
});

test('missing optional fields start with no field age, including timestamp zero', () => {
  const memory = new MatchMapMemory();
  memory.update({registration: {mapId: 'erangel', matrix: firstMatrix}, points: []}, frame('map'), 0);
  assert.equal(memory.current.result.position, null);
  assert.equal(memory.current.result.zone, null);
  assert.equal(memory.current.positionUpdatedAt, null);
  assert.equal(memory.current.zoneUpdatedAt, null);
  assert.equal(memory.current.mapUpdatedAt, 0);
});

test('reset clears match memory, so a later map cannot inherit old detections', () => {
  const memory = new MatchMapMemory();
  memory.update(recognized(), frame('old match'), 100);
  memory.reset();
  assert.equal(memory.snapshot(), null);
  assert.equal(memory.current, null);
  memory.update(recognized({position: null, zone: null}), frame('new match'), 500);
  assert.equal(memory.current.result.position, null);
  assert.equal(memory.current.result.zone, null);
});

test('a result without a frame or usable timestamp cannot replace the paired map', () => {
  const memory = new MatchMapMemory();
  memory.update(recognized(), frame('old'), 100);
  const before = memory.current;
  assert.equal(memory.update(recognized(), null, 200), false);
  assert.equal(memory.update(recognized(), frame('bad clock'), NaN), false);
  assert.equal(memory.current, before);
});

test('community anchor refresh adds, removes and moves IDs without refreshing map or field ages', () => {
  const memory = new MatchMapMemory();
  const source = frame('held map');
  const oldPoints = [{id: 'moved', visible: true, imageX: 400, imageY: 400},
    {id: 'removed', visible: true, imageX: 500, imageY: 500}];
  memory.update(recognized({registration: {mapId: 'erangel', matrix: firstMatrix, viewport: [0, 0, 960, 720]}, points: oldPoints}), source, 100);
  memory.update(recognized({registration: {mapId: 'erangel', matrix: firstMatrix, viewport: [0, 0, 960, 720]}, position: null, points: oldPoints}), source, 250);
  const before = memory.current;
  const metadata = {id: 'erangel', points: [{id: 'moved', x: .1, y: .2}, {id: 'added', x: .75, y: .25}]};
  assert.equal(memory.refreshPoints(metadata), true);
  const after = memory.current;
  assert.notEqual(after.result, before.result, 'New anchors must trigger a redraw');
  assert.equal(after.frame, before.frame);
  assert.equal(after.result.registration, before.result.registration);
  assert.equal(after.result.position, before.result.position);
  assert.equal(after.result.zone, before.result.zone);
  assert.deepEqual([after.mapUpdatedAt, after.positionUpdatedAt, after.zoneUpdatedAt], [250, 100, 250]);
  assert.deepEqual(after.result.points, [
    {id: 'moved', visible: true, imageX: 224, imageY: 168},
    {id: 'added', visible: true, imageX: 640, imageY: 200},
  ]);
  assert.deepEqual(before.result.points.map(point => point.id), ['moved', 'removed']);
  assert.equal(memory.refreshPoints({id: 'erangel', points: []}), true);
  assert.deepEqual(memory.current.result.points, []);
  assert.equal(memory.current.frame, source);
  assert.equal(memory.current.mapUpdatedAt, 250);
});

test('community anchor refresh clips both registration viewport and actual retained frame bounds', () => {
  const memory = new MatchMapMemory();
  const matrix = [[1000, 0, -100], [0, 1000, -100], [0, 0, 1]];
  memory.update(recognized({registration: {mapId: 'erangel', matrix, viewport: [50, 50, 1200, 900]}}), frame('held map'), 100);
  memory.refreshPoints({id: 'erangel', points: [
    {id: 'inside', x: .5, y: .5},
    {id: 'left-of-viewport', x: .12, y: .5},
    {id: 'top-of-frame', x: .5, y: 0},
    {id: 'bottom-of-frame', x: .5, y: .9},
    {id: 'invalid-world', x: 1.1, y: .5},
  ]});
  assert.deepEqual(memory.current.result.points, [
    {id: 'inside', visible: true, imageX: 400, imageY: 400},
    ...['left-of-viewport', 'top-of-frame', 'bottom-of-frame', 'invalid-world'].map(id =>
      ({id, visible: false, imageX: null, imageY: null})),
  ]);
});

test('community anchor refresh ignores absent snapshots and different map IDs', () => {
  const memory = new MatchMapMemory();
  assert.equal(memory.refreshPoints({id: 'erangel', points: []}), false);
  memory.update(recognized(), frame('held map'), 100);
  const before = memory.current;
  assert.equal(memory.refreshPoints({id: 'taego', points: []}), false);
  assert.equal(memory.refreshPoints(null), false);
  assert.equal(memory.current, before);
});

test('community anchor refresh cannot expose coordinates from invalid projection geometry', () => {
  const memory = new MatchMapMemory();
  memory.update(recognized({registration: {mapId: 'erangel', matrix: null}}), frame('held map'), 100);
  assert.equal(memory.refreshPoints({id: 'erangel', points: [{id: 'hidden', x: .2, y: .3}]}), true);
  assert.deepEqual(memory.current.result.points, [{id: 'hidden', visible: false, imageX: null, imageY: null}]);
});
