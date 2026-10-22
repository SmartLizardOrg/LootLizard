/** Lazy, local-only English OCR for conservative match-context evidence.
 * Never logs/persists recognized text or pixels. The caller owns throttling and
 * must not run this fallback beside map CV. No work/download starts on import.
 *
 * Pinned official worker protocol reviewed against:
 * https://github.com/naptha/tesseract.js/blob/v7.0.0/src/createWorker.js
 * https://github.com/naptha/tesseract.js/blob/v7.0.0/src/worker-script/index.js
 * https://github.com/naptha/tesseract.js/blob/v7.0.0/docs/api.md
 * Tesseract.js/core are Apache-2.0. The language npm package declares MIT;
 * its upstream trained-data repository carries Apache-2.0. Preserve both notices.
 */
export const OCR_ASSETS = Object.freeze({
  version: '7.0.0',
  worker: 'https://cdn.jsdelivr.net/npm/tesseract.js@7.0.0/dist/worker.min.js',
  core: 'https://cdn.jsdelivr.net/npm/tesseract.js-core@7.0.0',
  model: Object.freeze({
    url: 'https://cdn.jsdelivr.net/npm/@tesseract.js-data/eng@1.0.0/4.0.0_best_int/eng.traineddata.gz',
    sha256: '45b4cb346724ac1774f1c36f42f182b887bcdb28ebe63e6fff90ac41f3fcff91',
    bytes: 2952873, maxBytes: 3200000,
  }),
});

const MAX_INPUT_SIDE = 2400, MAX_INPUT_PIXELS = 4000000, MAX_WORDS = 192;
// Preserve small navigation glyphs with a narrow high-resolution band. Other
// crops target result headings and left menu/right result actions separately.
// The small overlap around left-menu headings is deduplicated before returning.
// Summed output budgets never exceed 770,000 pixels, with no image upscaling.
const REGIONS = Object.freeze([
  Object.freeze({id: 'navigation', x0: 0, y0: 0, x1: 1, y1: .16, pixels: 200000, side: 2000}),
  Object.freeze({id: 'results', x0: 0, y0: .16, x1: 1, y1: .60, pixels: 250000, side: 1200}),
  Object.freeze({id: 'left-actions', x0: 0, y0: .55, x1: .4, y1: .97, pixels: 160000, side: 900}),
  Object.freeze({id: 'right-actions', x0: .4, y0: .65, x1: 1, y1: .97, pixels: 140000, side: 1200}),
  Object.freeze({id: 'footer', x0: .70, y0: .97, x1: 1, y1: 1, pixels: 20000, side: 1200}),
]);

/** Also used inside the OCR worker, so this function has no module dependencies
 * other than the immutable OCR_ASSETS literal injected into its bootstrap.
 * HTTP cache is allowed; every returned model is checked again before use.
 */
export async function fetchVerifiedOcrModel({fetchImpl = globalThis.fetch, cryptoImpl = globalThis.crypto, signal} = {}) {
  const record = OCR_ASSETS.model;
  if (typeof fetchImpl !== 'function' || !cryptoImpl?.subtle?.digest) throw Error('ocr-model-unavailable');
  const response = await fetchImpl(record.url, {credentials: 'omit', cache: 'force-cache', redirect: 'error', signal});
  if (!response.ok || !response.body) {
    await response.body?.cancel().catch(() => {});
    throw Error('ocr-model-download-failed');
  }
  const declared = response.headers.get('content-length');
  if (declared !== null && (!/^\d+$/.test(declared) || Number(declared) > record.maxBytes)) {
    await response.body.cancel().catch(() => {});
    throw Error('ocr-model-byte-limit');
  }
  const reader = response.body.getReader(), chunks = [];
  let count = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      count += value.byteLength;
      if (count > record.maxBytes) throw Error('ocr-model-byte-limit');
      chunks.push(value);
    }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
  if (count !== record.bytes) throw Error('ocr-model-size-mismatch');
  const bytes = new Uint8Array(count);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  const digest = new Uint8Array(await cryptoImpl.subtle.digest('SHA-256', bytes));
  if (Array.from(digest, byte => byte.toString(16).padStart(2, '0')).join('') !== record.sha256) throw Error('ocr-model-checksum-mismatch');
  return bytes;
}

function validFrame(frame) {
  return Number.isInteger(frame?.width) && Number.isInteger(frame?.height) && frame.width >= 64 && frame.height >= 64 &&
    frame.width <= MAX_INPUT_SIDE && frame.height <= MAX_INPUT_SIDE && frame.width * frame.height <= MAX_INPUT_PIXELS &&
    frame.data instanceof Uint8ClampedArray && frame.data.length === frame.width * frame.height * 4;
}

export function contextCropPlan(width, height) {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 64 || height < 64 ||
      width > MAX_INPUT_SIDE || height > MAX_INPUT_SIDE || width * height > MAX_INPUT_PIXELS) throw Error('ocr-invalid-frame');
  return REGIONS.map(region => {
    const x0 = Math.floor(width * region.x0), x1 = Math.floor(width * region.x1);
    const y0 = Math.floor(height * region.y0), y1 = Math.floor(height * region.y1);
    const sourceWidth = x1 - x0, sourceHeight = y1 - y0;
    const scale = Math.min(1, region.side / Math.max(sourceWidth, sourceHeight), Math.sqrt(region.pixels / (sourceWidth * sourceHeight)));
    return {id: region.id, x0, y0, x1, y1,
      width: Math.max(1, Math.floor(sourceWidth * scale)), height: Math.max(1, Math.floor(sourceHeight * scale))};
  });
}

function cropPixels(frame, crop) {
  const data = new Uint8ClampedArray(crop.width * crop.height * 4);
  const sx = (crop.x1 - crop.x0) / crop.width, sy = (crop.y1 - crop.y0) / crop.height;
  for (let y = 0; y < crop.height; y++) for (let x = 0; x < crop.width; x++) {
    const source = (Math.min(crop.y1 - 1, crop.y0 + Math.floor((y + .5) * sy)) * frame.width +
      Math.min(crop.x1 - 1, crop.x0 + Math.floor((x + .5) * sx))) * 4;
    const target = (y * crop.width + x) * 4;
    // Composite translucent input onto black. This API expects ordinary opaque
    // capture frames, but must never accidentally interpret hidden RGB pixels.
    const alpha = frame.data[source + 3] / 255;
    data[target] = frame.data[source] * alpha; data[target + 1] = frame.data[source + 1] * alpha;
    data[target + 2] = frame.data[source + 2] * alpha; data[target + 3] = 255;
  }
  return {data, width: crop.width, height: crop.height};
}

function mappedWords(result, crop, frame) {
  const pending = [result?.data ?? result], words = [];
  let visited = 0;
  while (pending.length && visited++ < 2000 && words.length < MAX_WORDS) {
    const node = pending.pop();
    if (!node || typeof node !== 'object') continue;
    if (Array.isArray(node)) { for (let i = node.length - 1; i >= 0; i--) pending.push(node[i]); continue; }
    // Only leaf words have a confidence, text, and a box with no nested words.
    const box = node.bbox;
    if (typeof node.text === 'string' && Number.isFinite(node.confidence) && box &&
        !node.words && !node.lines && !node.paragraphs && !node.blocks) {
      const text = node.text.normalize('NFKC').replace(/\s+/g, ' ').trim().slice(0, 120);
      if (!text || node.confidence < 0 || node.confidence > 100 ||
          !['x0', 'y0', 'x1', 'y1'].every(key => Number.isFinite(box[key])) ||
          box.x0 < 0 || box.y0 < 0 || box.x1 > crop.width || box.y1 > crop.height || box.x1 <= box.x0 || box.y1 <= box.y0) continue;
      const sx = (crop.x1 - crop.x0) / crop.width, sy = (crop.y1 - crop.y0) / crop.height;
      words.push({text, confidence: node.confidence, bbox: {
        x0: Math.max(0, crop.x0 + box.x0 * sx), y0: Math.max(0, crop.y0 + box.y0 * sy),
        x1: Math.min(frame.width, crop.x0 + box.x1 * sx), y1: Math.min(frame.height, crop.y0 + box.y1 * sy),
      }});
    } else for (const key of ['blocks', 'paragraphs', 'lines', 'words']) if (node[key]) pending.push(node[key]);
  }
  return words;
}

function readingOrder(words) {
  const unique = [];
  for (const word of words) {
    const a = word.bbox, key = word.text.toUpperCase();
    const duplicate = unique.findIndex(other => {
      if (other.text.toUpperCase() !== key) return false;
      const b = other.bbox;
      const intersection = Math.max(0, Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0)) *
        Math.max(0, Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0));
      return intersection / Math.min((a.x1 - a.x0) * (a.y1 - a.y0), (b.x1 - b.x0) * (b.y1 - b.y0)) >= .65;
    });
    if (duplicate === -1) unique.push(word);
    else if (word.confidence > unique[duplicate].confidence) unique[duplicate] = word;
  }
  const lines = [];
  for (const word of unique.sort((a, b) => a.bbox.y0 - b.bbox.y0 || a.bbox.x0 - b.bbox.x0)) {
    const box = word.bbox;
    const line = lines.find(row => Math.min(row.y1, box.y1) - Math.max(row.y0, box.y0) >=
      Math.min(row.y1 - row.y0, box.y1 - box.y0) * .5);
    if (line) {line.words.push(word); line.y0 = Math.min(line.y0, box.y0); line.y1 = Math.max(line.y1, box.y1);}
    else lines.push({y0: box.y0, y1: box.y1, words: [word]});
  }
  return lines.sort((a, b) => a.y0 - b.y0).flatMap(line => line.words.sort((a, b) => a.bbox.x0 - b.bbox.x0));
}

async function encodeCrop(image) {
  const canvas = typeof OffscreenCanvas === 'function' ? new OffscreenCanvas(image.width, image.height) :
    globalThis.document?.createElement('canvas');
  if (!canvas) throw Error('ocr-canvas-unavailable');
  canvas.width = image.width; canvas.height = image.height;
  canvas.getContext('2d').putImageData(new ImageData(image.data, image.width, image.height), 0, 0);
  const blob = canvas.convertToBlob ? await canvas.convertToBlob({type: 'image/png'}) :
    await new Promise((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(Error('ocr-encode-failed')), 'image/png'));
  return new Uint8Array(await blob.arrayBuffer());
}

/** Thin RPC adapter to the reviewed pinned official worker. Keeping the native
 * Worker handle from creation lets a deadline terminate even failed startup;
 * createWorker() only exposes its handle after all initialization has finished.
 */
function createPinnedWorker() {
  if (typeof Worker !== 'function' || !globalThis.crypto?.subtle) throw Error('ocr-worker-unavailable');
  const bootstrap = `const OCR_ASSETS=${JSON.stringify(OCR_ASSETS)};
const fetchVerifiedOcrModel=${fetchVerifiedOcrModel.toString()};
const nativeFetch=self.fetch.bind(self);
self.fetch=async(input,options)=>{
  const url=typeof input==='string'?input:input.url;
  if(url===OCR_ASSETS.model.url){
    const bytes=await fetchVerifiedOcrModel({fetchImpl:nativeFetch,cryptoImpl:self.crypto});
    return new Response(bytes,{headers:{'Content-Type':'application/gzip'}});
  }
  return nativeFetch(input,options);
};
importScripts(OCR_ASSETS.worker);`;
  const url = URL.createObjectURL(new Blob([bootstrap], {type: 'text/javascript'}));
  let native;
  try { native = new Worker(url); }
  catch { URL.revokeObjectURL(url); throw Error('ocr-worker-unavailable'); }
  const pending = new Map();
  let next = 0, stopped = false;
  const terminate = () => {
    if (stopped) return;
    stopped = true; native.terminate(); URL.revokeObjectURL(url);
    for (const task of pending.values()) task.reject(Error('ocr-worker-stopped'));
    pending.clear();
  };
  native.onmessage = ({data}) => {
    const task = pending.get(data?.jobId);
    if (!task || !['resolve', 'reject'].includes(data.status)) return;
    pending.delete(data.jobId);
    data.status === 'resolve' ? task.resolve({data: data.data}) : task.reject(Error('ocr-engine-failed'));
  };
  native.onerror = () => terminate();
  const rpc = (action, payload, transfer = []) => new Promise((resolve, reject) => {
    if (stopped) { reject(Error('ocr-worker-stopped')); return; }
    const jobId = `context-${++next}`;
    pending.set(jobId, {resolve, reject});
    try { native.postMessage({workerId: 'lootlizard-context', jobId, action, payload}, transfer); }
    catch { pending.delete(jobId); reject(Error('ocr-worker-message-failed')); }
  });
  const ready = (async () => {
    await rpc('load', {options: {lstmOnly: true, corePath: OCR_ASSETS.core, logging: false}});
    await rpc('loadLanguage', {langs: 'eng', options: {
      langPath: OCR_ASSETS.model.url.slice(0, OCR_ASSETS.model.url.lastIndexOf('/')),
      cacheMethod: 'none', gzip: true, lstmOnly: true,
    }});
    await rpc('initialize', {langs: 'eng', oem: 1, config: {load_system_dawg: '0', load_freq_dawg: '0'}});
    await rpc('setParameters', {params: {tessedit_pageseg_mode: '11', user_defined_dpi: '120', classify_enable_learning: '0'}});
  })();
  ready.catch(() => {});
  return {ready, terminate, async recognize(image) {
    await ready;
    const bytes = await encodeCrop(image);
    return rpc('recognize', {image: bytes, options: {}, output: {text: false, blocks: true}}, [bytes.buffer]);
  }};
}

/** One reusable worker, one active read, no queue. Reasons are fixed codes:
 * recognized names/session strings are returned only in ephemeral word objects.
 */
export function createMatchContextReader({workerFactory = createPinnedWorker, initTimeoutMs = 45000, timeoutMs = 8000} = {}) {
  if (typeof workerFactory !== 'function' || ![initTimeoutMs, timeoutMs].every(value => Number.isFinite(value) && value >= 1 && value <= 120000)) throw Error('ocr-invalid-options');
  let worker = null, starting = null, preparation = null, ready = false, busy = false, generation = 0;
  let cancelRead = null, cancelPrepare = null;
  const safeTerminate = candidate => { try { Promise.resolve(candidate?.terminate?.()).catch(() => {}); } catch {} };
  const terminate = () => {
    generation++; ready = false; safeTerminate(worker); worker = null; starting = null; preparation = null;
    cancelPrepare?.();
    cancelRead?.();
  };
  async function ensureWorker(token) {
    if (!starting) starting = Promise.resolve().then(() => {
      if (token !== generation) throw Error('ocr-cancelled');
      return workerFactory();
    }).then(candidate => {
      if (token !== generation) { safeTerminate(candidate); throw Error('ocr-cancelled'); }
      if (!candidate || typeof candidate.recognize !== 'function' || typeof candidate.terminate !== 'function') throw Error('ocr-invalid-worker');
      worker = candidate;
      return Promise.resolve(candidate.ready).then(() => {
        if (token !== generation) throw Error('ocr-cancelled');
        ready = true; return candidate;
      });
    });
    return starting;
  }
  // The scan loop may start this without awaiting it and continue map CV on
  // following frames. Startup never crops a frame or submits recognition work.
  // Every failure resolves false, including cancellation and a startup deadline.
  function prepare() {
    if (ready) return Promise.resolve(true);
    if (preparation) return preparation;
    const token = generation;
    let timer, cancel;
    const cancelled = new Promise(resolve => { cancel = () => resolve(false); cancelPrepare = cancel; });
    const operation = Promise.race([
      ensureWorker(token).then(() => true, () => false), cancelled,
      new Promise(resolve => { timer = setTimeout(() => resolve(false), initTimeoutMs); }),
    ]).then(ok => {
      if (!ok && token === generation) terminate();
      return Boolean(ok && token === generation && ready);
    }).catch(() => {
      if (token === generation) terminate();
      return false;
    }).finally(() => {
      clearTimeout(timer);
      if (preparation === operation) preparation = null;
      if (cancelPrepare === cancel) cancelPrepare = null;
    });
    preparation = operation;
    return operation;
  }
  async function read(frame, {signal} = {}) {
    const empty = reason => ({status: 'unknown', reason, width: frame?.width || 0, height: frame?.height || 0, words: []});
    if (!validFrame(frame)) return empty('ocr-invalid-frame');
    if (busy) return empty('ocr-busy');
    if (signal?.aborted) return empty('ocr-cancelled');
    busy = true;
    const token = generation;
    let timer;
    const cancelled = new Promise((_, reject) => { cancelRead = () => reject(Error('ocr-cancelled')); });
    const abort = () => terminate();
    signal?.addEventListener('abort', abort, {once: true});
    const bounded = async (operation, limit, reason) => {
      try { return await Promise.race([operation, cancelled, new Promise((_, reject) => {
        timer = setTimeout(() => reject(Error(reason)), limit);
      })]); } finally { clearTimeout(timer); }
    };
    try {
      const readyWorker = await bounded(ensureWorker(token), initTimeoutMs, 'ocr-startup-timeout');
      const work = (async () => {
        const words = [];
        for (const crop of contextCropPlan(frame.width, frame.height)) {
          if (token !== generation) throw Error('ocr-cancelled');
          const result = await readyWorker.recognize(cropPixels(frame, crop));
          words.push(...mappedWords(result, crop, frame));
          if (words.length >= MAX_WORDS) break;
        }
        return readingOrder(words).slice(0, MAX_WORDS);
      })();
      const words = await bounded(work, timeoutMs, 'ocr-read-timeout');
      if (token !== generation) return empty('ocr-cancelled');
      return {status: words.length ? 'ok' : 'unknown', reason: words.length ? 'ocr-words-ready' : 'ocr-no-words', width: frame.width, height: frame.height, words};
    } catch (error) {
      const code = ['ocr-cancelled', 'ocr-startup-timeout', 'ocr-read-timeout'].includes(error?.message) ? error.message : 'ocr-unavailable';
      terminate();
      return empty(code);
    } finally {
      clearTimeout(timer); signal?.removeEventListener('abort', abort); cancelRead = null; busy = false;
    }
  }
  return Object.freeze({read, prepare, terminate, getState: () => ({busy, initialized: Boolean(worker), ready, version: OCR_ASSETS.version})});
}
