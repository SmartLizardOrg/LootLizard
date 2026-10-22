/** Capture requests are preferences/constraints, never proof of actual settings. */
const CAPTURE_RATES = new Set([1, 3]);
const DISPLAY_SURFACES = new Set(['monitor', 'window', 'browser']);

function captureRate(fps) {
  if (!CAPTURE_RATES.has(fps)) throw new RangeError('Choose a capture rate of 1 or 3 FPS.');
  return fps;
}

function positiveInteger(value, name) {
  if (!Number.isSafeInteger(value) || value < 1) throw new RangeError(`${name} must be a positive integer.`);
  return value;
}

export function displayMediaOptions(fps = 1) {
  captureRate(fps);
  return {
    video: {
      frameRate: {ideal: fps, max: fps},
      width: {ideal: 2400, max: 2400},
      height: {ideal: 2400, max: 2400},
    },
    audio: false,
    selfBrowserSurface: 'exclude',
  };
}

/** Do not retain device IDs, capture labels, or other source-identifying fields. */
export function readCaptureSettings(track) {
  let actual;
  try { actual = track?.getSettings?.(); } catch { return {}; }
  if (!actual || typeof actual !== 'object') return {};
  const settings = {};
  for (const key of ['width', 'height']) {
    if (Number.isSafeInteger(actual[key]) && actual[key] > 0) settings[key] = actual[key];
  }
  if (typeof actual.frameRate === 'number' && Number.isFinite(actual.frameRate) && actual.frameRate >= 0)
    settings.frameRate = actual.frameRate;
  if (DISPLAY_SURFACES.has(actual.displaySurface)) settings.displaySurface = actual.displaySurface;
  return settings;
}

function constraintError(error) {
  const names = new Set(['OverconstrainedError', 'NotSupportedError', 'InvalidStateError', 'TypeError', 'Error']);
  const result = {name: names.has(error?.name) ? error.name : 'Error'};
  if (['frameRate', 'width', 'height', 'aspectRatio'].includes(error?.constraint)) result.constraint = error.constraint;
  return result;
}

export async function applyCaptureRate(track, fps = 1) {
  captureRate(fps);
  let error;
  if (!track || track.readyState === 'ended') error = {name: 'InvalidStateError'};
  else if (typeof track.applyConstraints !== 'function') error = {name: 'NotSupportedError'};
  else {
    try {
      // Keep existing size bounds when changing the rate: applyConstraints
      // replaces the previous constraint set rather than merging it.
      let previous = displayMediaOptions(fps).video;
      if (typeof track.getConstraints === 'function') {
        const current = track.getConstraints();
        if (current && typeof current === 'object') previous = current;
      }
      await track.applyConstraints({...previous, frameRate: {ideal: fps, max: fps}});
    } catch (failure) { error = constraintError(failure); }
  }
  return {requestedFrameRate: fps, applied: !error, settings: readCaptureSettings(track), ...(error ? {error} : {})};
}

/** Keep both pixel and side bounds, including very narrow source dimensions. */
export function boundedFrameSize(width, height, maxSide = 2400, maxPixels = 4_000_000) {
  positiveInteger(width, 'Width'); positiveInteger(height, 'Height');
  positiveInteger(maxSide, 'Maximum side'); positiveInteger(maxPixels, 'Maximum pixels');
  const scale = Math.min(1, maxSide / Math.max(width, height), Math.sqrt(maxPixels / (width * height)));
  let scaledWidth = Math.max(1, Math.floor(width * scale));
  let scaledHeight = Math.max(1, Math.floor(height * scale));
  // Rounding a subpixel short side up to one must not exceed the pixel budget.
  if (scaledWidth * scaledHeight > maxPixels) {
    if (scaledWidth >= scaledHeight) scaledWidth = Math.max(1, Math.floor(maxPixels / scaledHeight));
    else scaledHeight = Math.max(1, Math.floor(maxPixels / scaledWidth));
  }
  return {width: scaledWidth, height: scaledHeight};
}

/** Assigning even an unchanged canvas dimension clears/reallocates its bitmap. */
export function setSamplerSize(canvas, width, height) {
  positiveInteger(width, 'Width'); positiveInteger(height, 'Height');
  let changed = false;
  if (canvas.width !== width) { canvas.width = width; changed = true; }
  if (canvas.height !== height) { canvas.height = height; changed = true; }
  return changed;
}
