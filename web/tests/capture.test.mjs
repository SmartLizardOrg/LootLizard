import test from 'node:test';
import assert from 'node:assert/strict';
import {displayMediaOptions, readCaptureSettings, applyCaptureRate, boundedFrameSize, setSamplerSize} from '../app/capture.mjs';

test('capture starts at one FPS with bounded size and supports only the two explicit rates', () => {
  assert.deepEqual(displayMediaOptions(), {
    video: {frameRate: {ideal: 1, max: 1}, width: {ideal: 2400, max: 2400}, height: {ideal: 2400, max: 2400}},
    audio: false, selfBrowserSurface: 'exclude',
  });
  assert.deepEqual(displayMediaOptions(3).video.frameRate, {ideal: 3, max: 3});
  const changed = displayMediaOptions(); changed.video.width.max = 10;
  assert.equal(displayMediaOptions().video.width.max, 2400, 'Callers do not share mutable options');
  for (const rate of [0, 2, 5, -1, NaN, Infinity, '1', true, null]) assert.throws(() => displayMediaOptions(rate), RangeError);
});

test('actual settings disclose only dimensions, actual rate and known surface kind', () => {
  const track = {getSettings: () => ({width: 1920, height: 1080, frameRate: 2.5, displaySurface: 'monitor',
    deviceId: 'private-device', label: 'private-window', groupId: 'private-group', cursor: 'always'})};
  assert.deepEqual(readCaptureSettings(track), {width: 1920, height: 1080, frameRate: 2.5, displaySurface: 'monitor'});
  assert.deepEqual(readCaptureSettings({getSettings: () => ({width: '1920', height: -1, frameRate: Infinity, displaySurface: 'private-label'})}), {});
  assert.deepEqual(readCaptureSettings({getSettings: () => ({frameRate: 0})}), {frameRate: 0});
  assert.deepEqual(readCaptureSettings({getSettings: () => {throw Error('unavailable');}}), {});
  assert.deepEqual(readCaptureSettings(null), {});
});

test('changing rate preserves resolution bounds and reports actual settings rather than requested FPS', async () => {
  const previous = {width: {max: 2400}, height: {max: 2400}, frameRate: {max: 1}};
  let received;
  const result = await applyCaptureRate({getConstraints: () => previous,
    applyConstraints: async constraints => {received = constraints;},
    getSettings: () => ({width: 2400, height: 1350, frameRate: 2.8, displaySurface: 'window', deviceId: 'private'})}, 3);
  assert.deepEqual(received, {width: {max: 2400}, height: {max: 2400}, frameRate: {ideal: 3, max: 3}});
  assert.deepEqual(previous.frameRate, {max: 1}, 'Existing constraints are not mutated');
  assert.deepEqual(result, {requestedFrameRate: 3, applied: true,
    settings: {width: 2400, height: 1350, frameRate: 2.8, displaySurface: 'window'}});
});

test('a rejected constraint keeps actual settings and a bounded error instead of claiming success', async () => {
  const result = await applyCaptureRate({applyConstraints: async () => {
    throw {name: 'OverconstrainedError', constraint: 'frameRate', message: 'private source details'};
  }, getSettings: () => ({width: 2560, height: 1440, frameRate: 5, deviceId: 'private'})});
  assert.deepEqual(result, {requestedFrameRate: 1, applied: false,
    settings: {width: 2560, height: 1440, frameRate: 5}, error: {name: 'OverconstrainedError', constraint: 'frameRate'}});
  assert.equal(JSON.stringify(result).includes('private'), false);
  const unknown = await applyCaptureRate({applyConstraints: async () => {throw {name: 'private', constraint: 'private'};}});
  assert.deepEqual(unknown.error, {name: 'Error'});
});

test('rate changes retain explicit size bounds when current constraints are unavailable', async () => {
  for (const track of [{}, {getConstraints: () => null}]) {
    let received;
    track.applyConstraints = async value => {received = value;};
    const result = await applyCaptureRate(track);
    assert.equal(result.applied, true);
    assert.deepEqual(received, displayMediaOptions().video);
  }
});

test('unsupported and ended tracks return actual diagnostics without applying constraints', async () => {
  const unsupported = await applyCaptureRate({getSettings: () => ({frameRate: 5})});
  assert.deepEqual(unsupported, {requestedFrameRate: 1, applied: false, settings: {frameRate: 5}, error: {name: 'NotSupportedError'}});
  const ended = await applyCaptureRate({readyState: 'ended', applyConstraints: () => assert.fail('Ended track is not reconfigured')});
  assert.deepEqual(ended.error, {name: 'InvalidStateError'});
  await assert.rejects(applyCaptureRate({}, 5), RangeError);
});

test('frame bounds retain ordinary aspect ratios and both limits without upscaling', () => {
  assert.deepEqual(boundedFrameSize(2560, 1440), {width: 2400, height: 1350});
  assert.deepEqual(boundedFrameSize(3840, 2160), {width: 2400, height: 1350});
  assert.deepEqual(boundedFrameSize(2400, 2400), {width: 2000, height: 2000});
  assert.deepEqual(boundedFrameSize(1280, 720), {width: 1280, height: 720});
  assert.deepEqual(boundedFrameSize(720, 1280, 640), {width: 360, height: 640});
  for (const [width, height] of [[1, 9000], [9000, 1], [100000, 100000], [1, 1], [700, 2100]]) {
    for (const maxPixels of [1, 7, 100, 4_000_000]) {
      const size = boundedFrameSize(width, height, 2400, maxPixels);
      assert.ok(size.width >= 1 && size.height >= 1);
      assert.ok(size.width <= width && size.height <= height);
      assert.ok(Math.max(size.width, size.height) <= 2400);
      assert.ok(size.width * size.height <= maxPixels);
    }
  }
});

test('invalid frame dimensions and budgets are rejected before allocating a canvas', () => {
  for (const value of [0, -1, 1.5, NaN, Infinity, '1920', true, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => boundedFrameSize(value, 1080), RangeError);
    assert.throws(() => boundedFrameSize(1920, value), RangeError);
    assert.throws(() => boundedFrameSize(1920, 1080, value), RangeError);
    assert.throws(() => boundedFrameSize(1920, 1080, 2400, value), RangeError);
  }
});

test('unchanged sampler dimensions do not reset the canvas bitmap', () => {
  let width = 2400, height = 1350;
  const writes = [];
  const canvas = {get width() {return width;}, set width(value) {writes.push(['width', value]); width = value;},
    get height() {return height;}, set height(value) {writes.push(['height', value]); height = value;}};
  assert.equal(setSamplerSize(canvas, 2400, 1350), false);
  assert.deepEqual(writes, []);
  assert.equal(setSamplerSize(canvas, 2400, 1200), true);
  assert.deepEqual(writes, [['height', 1200]]);
  assert.equal(setSamplerSize(canvas, 1800, 1000), true);
  assert.deepEqual(writes.slice(1), [['width', 1800], ['height', 1000]]);
  assert.throws(() => setSamplerSize(canvas, 0, 10), RangeError);
});
