import test from 'node:test';
import assert from 'node:assert/strict';
import {mapViewport, sourcePreviewSize} from '../app/map-view.mjs';

test('registered map bounds exclude surrounding gameplay and preserve source offsets', () => {
  assert.deepEqual(mapViewport([[640, 0, 160], [0, 640, 40], [0, 0, 1]], 960, 720),
    {x: 160, y: 40, width: 640, height: 640});
  assert.deepEqual(mapViewport([[1440, 0, 560], [0, 1440, 0], [0, 0, 1]], 2560, 1440),
    {x: 560, y: 0, width: 1440, height: 1440});
});

test('partially visible or rotated maps remain inside the available source pixels', () => {
  assert.deepEqual(mapViewport([[800, 0, -100], [0, 800, -40], [0, 0, 1]], 640, 480),
    {x: 0, y: 0, width: 640, height: 480});
  assert.deepEqual(mapViewport([[400, -100, 200], [100, 400, 30], [0, 0, 1]], 960, 720),
    {x: 100, y: 30, width: 500, height: 500});
});

test('invalid, degenerate and entirely off-screen map transforms cannot reveal a main image', () => {
  for (const matrix of [null, [[1]], [[1, 0, NaN], [0, 1, 0], [0, 0, 1]],
    [[1, 0, 0], [0, 1, 0], [0, 0, 0]], [[0, 0, 1], [0, 0, 1], [0, 0, 1]],
    [[100, 0, 1000], [0, 100, 1000], [0, 0, 1]]]) {
    assert.equal(mapViewport(matrix, 960, 720), null);
  }
});

test('source thumbnails fit 240 by 135, retain aspect ratio and never upscale', () => {
  assert.deepEqual(sourcePreviewSize(2560, 1440), {width: 240, height: 135});
  assert.deepEqual(sourcePreviewSize(960, 720), {width: 180, height: 135});
  assert.deepEqual(sourcePreviewSize(900, 1800), {width: 67, height: 135});
  assert.deepEqual(sourcePreviewSize(40, 40), {width: 40, height: 40});
  for (const dimensions of [[0, 0], [NaN, 800], [240.5, 100]]) assert.equal(sourcePreviewSize(...dimensions), null);
});
