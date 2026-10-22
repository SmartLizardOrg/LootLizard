import test from 'node:test';
import assert from 'node:assert/strict';
import {fitView, viewTransform, panView, zoomViewAt, MIN_ZOOM, MAX_ZOOM} from '../app/map-navigation.mjs';

const square = Object.freeze({mapWidth: 1000, mapHeight: 1000, width: 600, height: 600});
const close = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-9,
  `Expected ${actual} to be within 1e-9 of ${expected}`);
const at = (transform, x, y) => [
  (x - transform.offsetX) / transform.drawWidth,
  (y - transform.offsetY) / transform.drawHeight,
];

test('fit shows the whole map and centers unavoidable letterboxing', () => {
  assert.equal(MIN_ZOOM, 1);
  assert.equal(MAX_ZOOM, 8);
  assert.notEqual(fitView(), fitView());
  const metrics = {mapWidth: 1000, mapHeight: 1000, width: 800, height: 600};
  assert.deepEqual(viewTransform(fitView(), metrics), {
    zoom: 1, centerX: 0.5, centerY: 0.5,
    scale: 0.6, drawWidth: 600, drawHeight: 600, offsetX: 100, offsetY: 0,
  });
  assert.deepEqual(panView(fitView(), 999, -999, metrics), fitView());
});

test('zoom keeps the map coordinate under the pointer until an edge is reached', () => {
  const pointer = [210, 380];
  const before = viewTransform(fitView(), square);
  const state = zoomViewAt(fitView(), 2, ...pointer, square);
  const after = viewTransform(state, square);
  const oldPoint = at(before, ...pointer);
  const newPoint = at(after, ...pointer);
  close(newPoint[0], oldPoint[0]);
  close(newPoint[1], oldPoint[1]);
  assert.equal(after.zoom, 2);
  const restored = zoomViewAt(state, 0.5, ...pointer, square);
  assert.deepEqual(restored, fitView());
});

test('drag direction follows the pointer, in CSS pixels regardless of source size', () => {
  const state = {zoom: 2, centerX: 0.5, centerY: 0.5};
  const before = viewTransform(state, square);
  const after = viewTransform(panView(state, 80, -40, square), square);
  close(after.offsetX - before.offsetX, 80);
  close(after.offsetY - before.offsetY, -40);
  const largerSource = {...square, mapWidth: 2000, mapHeight: 2000};
  assert.deepEqual(panView(state, 80, -40, square), panView(state, 80, -40, largerSource));
});

test('panning cannot expose empty space past any map edge', () => {
  const state = {zoom: 4, centerX: 0.5, centerY: 0.5};
  const topLeft = viewTransform(panView(state, 100000, 100000, square), square);
  close(topLeft.offsetX, 0);
  close(topLeft.offsetY, 0);
  const bottomRight = viewTransform(panView(state, -100000, -100000, square), square);
  close(bottomRight.offsetX + bottomRight.drawWidth, square.width);
  close(bottomRight.offsetY + bottomRight.drawHeight, square.height);
});

test('letterboxed axes stay centered even when the other axis is pannable', () => {
  const metrics = {mapWidth: 2000, mapHeight: 500, width: 600, height: 600};
  const view = viewTransform(panView({zoom: 2, centerX: 0.5, centerY: 0.5}, 60, 500, metrics), metrics);
  assert.equal(view.centerY, 0.5);
  close(view.offsetY, 150);
  close(view.offsetX, -240);
  const clampedZoom = zoomViewAt(fitView(), 2, 10, 10, metrics);
  const anchored = viewTransform(clampedZoom, metrics);
  assert.equal(anchored.centerY, 0.5);
  close(anchored.offsetY, 150);
});

test('zoom limits clamp safely and fit recovers the full map', () => {
  const maxed = zoomViewAt(fitView(), 100000, 0, 0, square);
  assert.equal(maxed.zoom, MAX_ZOOM);
  assert.equal(viewTransform(maxed, square).offsetX, 0);
  const maxAgain = zoomViewAt(maxed, Number.MAX_VALUE, 600, 600, square);
  assert.equal(maxAgain.zoom, MAX_ZOOM);
  const fit = zoomViewAt(maxed, 0.000001, 0, 0, square);
  assert.deepEqual(fit, fitView());
  assert.deepEqual(zoomViewAt(fitView(), 0.5, 10, 10, square), fitView());
});

test('normalized focus survives source resizing and clamps appropriately on viewport resize', () => {
  const state = {zoom: 4, centerX: 0.7, centerY: 0.3};
  const original = viewTransform(state, square);
  const resizedSource = viewTransform(state, {...square, mapWidth: 4000, mapHeight: 4000});
  close(original.offsetX, resizedSource.offsetX);
  close(original.offsetY, resizedSource.offsetY);
  assert.equal(resizedSource.centerX, 0.7);
  assert.equal(resizedSource.centerY, 0.3);
  const wide = viewTransform(state, {...square, width: 3000});
  assert.equal(wide.centerX, 0.5);
  close(wide.offsetX, (3000 - wide.drawWidth) / 2);
  assert.equal(wide.centerY, 0.3);
});

test('input states and metrics are never mutated', () => {
  const state = Object.freeze({zoom: 2, centerX: 0.5, centerY: 0.5});
  for (const next of [panView(state, 30, 50, square), zoomViewAt(state, 1.5, 300, 300, square)]) {
    assert.notEqual(next, state);
    assert.deepEqual(state, {zoom: 2, centerX: 0.5, centerY: 0.5});
  }
  viewTransform(state, square);
});

test('invalid metrics and state cannot produce NaN, infinity or throw', () => {
  for (const metrics of [null, {}, {...square, width: 0}, {...square, height: NaN},
    {...square, mapWidth: Infinity}, {...square, mapHeight: -1},
    {...square, mapWidth: 1e-300, mapHeight: 1e-300, width: 1e8, height: 1e8},
    {...square, mapWidth: Number.MIN_VALUE, mapHeight: Number.MIN_VALUE},
    {...square, width: Number.MAX_VALUE}]) {
    assert.equal(viewTransform(fitView(), metrics), null);
    assert.deepEqual(panView(null, 30, 50, metrics), fitView());
    assert.deepEqual(zoomViewAt(null, 2, 300, 300, metrics), fitView());
  }
  for (const state of [undefined, null, {}, {zoom: NaN, centerX: Infinity, centerY: 'bad'}]) {
    assert.deepEqual(viewTransform(state, square), viewTransform(fitView(), square));
  }
  assert.deepEqual(panView(fitView(), Infinity, NaN, square), fitView());
  for (const factor of [0, -1, NaN, Infinity]) {
    assert.deepEqual(zoomViewAt(fitView(), factor, 300, 300, square), fitView());
  }
  const extremes = panView({zoom: 8, centerX: 0.5, centerY: 0.5}, Number.MAX_VALUE, -Number.MAX_VALUE, square);
  assert.ok(Object.values(viewTransform(extremes, square)).every(Number.isFinite));
});
