import test from 'node:test';
import assert from 'node:assert/strict';
import {CaptureSession, orderTargets} from '../poc/session.mjs';

test('stopping clears a displayed result and rejects the in-flight reply', () => {
  const session = new CaptureSession();
  session.begin('screen');
  session.accept(session.issue(), {points: ['old']}, 10);
  const pending = session.issue();
  session.stop();
  assert.equal(session.accept(pending, {points: ['late']}, 20), false);
  assert.equal(session.result, null);
  assert.equal(session.updatedAt, 0);
  assert.deepEqual(session.snapshot(), {frameEpoch: pending.epoch + 1, sharing: false, source: null, active: false});
});

test('a new capture cannot accept tickets from the replaced capture', () => {
  const session = new CaptureSession();
  session.begin('screen');
  const old = session.issue();
  session.begin('image');
  const current = session.issue();
  assert.equal(old.sequence, current.sequence);
  assert.notEqual(old.epoch, current.epoch);
  assert.equal(session.accept(old, {points: ['wrong capture']}), false);
  assert.equal(session.accept(current, {points: ['current capture']}), true);
  assert.deepEqual(session.result.points, ['current capture']);
});

test('only the latest issued frame can replace the display', () => {
  const session = new CaptureSession();
  session.begin('screen');
  const earlier = session.issue(), latest = session.issue();
  assert.equal(session.accept(earlier, {mapId: 'old'}), false);
  assert.equal(session.accept(latest, {mapId: 'current'}), true);
  assert.equal(session.accept(latest, {mapId: 'duplicate'}), false);
  assert.equal(session.result.mapId, 'current');
});

test('a current unknown frame replaces the prior recognized map result', () => {
  const session = new CaptureSession();
  session.begin('screen');
  session.accept(session.issue(), {registration: {mapId: 'demo'}, points: ['room']});
  const unknown = {registration: null, position: null, zone: null, points: []};
  assert.equal(session.accept(session.issue(), unknown), true);
  assert.deepEqual(session.result, unknown);
});

test('changing setup/context invalidates pending work while keeping the stream active', () => {
  const session = new CaptureSession();
  session.begin('screen');
  const old = session.issue();
  session.invalidate();
  assert.equal(session.snapshot().sharing, true);
  assert.equal(session.result, null);
  assert.equal(session.accept(old, {points: ['old context']}), false);
  assert.equal(session.accept(session.issue(), {points: ['new context']}), true);
});

test('a stopped session cannot issue or accept work', () => {
  const session = new CaptureSession();
  assert.equal(session.issue(), null);
  assert.equal(session.accept({epoch: 0, sequence: 1}, {}), false);
  session.begin('demo');
  assert.equal(session.snapshot().sharing, false);
  assert.equal(session.snapshot().active, true);
});

test('inside-zone targets rank before nearer outside targets', () => {
  const map = {size_m: 8000, points: [{id: 'near', x: .1, y: .1}, {id: 'inside', x: .5, y: .5}]};
  const targets = orderTargets(map, {x: .1, y: .1}, {centerX: .5, centerY: .5, radius: .1});
  assert.deepEqual(targets.map(point => point.id), ['inside', 'near']);
  assert.equal(targets[0].inside, true);
  assert.equal(targets[1].distance, 0);
});

test('missing player/circle does not invent distances or zone membership', () => {
  const map = {size_m: 8000, points: [{id: 'b', x: .7, y: .2}, {id: 'a', x: .2, y: .1}]};
  const targets = orderTargets(map, null, null);
  assert.deepEqual(targets.map(point => point.id), ['a', 'b']);
  assert.ok(targets.every(point => point.distance === null && point.inside === null));
});
