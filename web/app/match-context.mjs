/** Conservative English PUBG menu evidence from LOCAL OCR, never missing-map time.
 *
 * The caller supplies reading-order OCR words with confidence and pixel bbox,
 * and must discard old-source/OCR replies before observe(). No screen pixels,
 * arbitrary OCR text, or player names are retained here. Other game languages,
 * changed layouts, occluded menus, and weak OCR intentionally remain unknown.
 */
const normalize = value => String(value).normalize('NFKC').toUpperCase().replace(/[^A-Z0-9#]+/g, ' ').trim();

function textWords(observation) {
  const {words, width, height} = observation || {};
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0 ||
      !Array.isArray(words) || words.length > 1000) return null;
  return words.filter(word => {
    const box = word?.bbox;
    return typeof word?.text === 'string' && word.text.length <= 160 &&
      Number.isFinite(word.confidence) && word.confidence >= 70 &&
      box && [box.x0, box.y0, box.x1, box.y1].every(Number.isFinite) &&
      0 <= box.x0 && box.x0 < box.x1 && box.x1 <= width &&
      0 <= box.y0 && box.y0 < box.y1 && box.y1 <= height;
  }).map(word => ({text: normalize(word.text),
    x: (word.bbox.x0 + word.bbox.x1) / (2 * width),
    y: (word.bbox.y0 + word.bbox.y1) / (2 * height)}));
}

const text = words => words.map(word => word.text).join(' ');
const tokens = words => new Set(words.flatMap(word => word.text.split(' ')));
const hasPhrase = (words, phrase) => (` ${text(words)} `).includes(` ${phrase} `);
const unknown = reason => ({context: 'unknown', cues: [], reason});

/** Positive multi-cue lobby/results evidence; this does not identify a process. */
export function classifyMatchContext(observation) {
  const words = textWords(observation);
  if (!words) return unknown('invalid-observation');
  const all = tokens(words);
  // Return-to-lobby alone occurs in the in-match pause menu. Never clear there.
  if (all.has('RESUME') || all.has('INVENTORY') || hasPhrase(words, 'SYSTEM MENU')) return unknown('in-match-menu');

  const navigation = tokens(words.filter(word => word.y <= .14));
  const nav = ['PLAY', 'CAREER', 'CUSTOMIZE', 'WORKSHOP', 'STORE'].filter(token => navigation.has(token));
  const actions = tokens(words.filter(word => word.x <= .35 && word.y >= .77));
  const modes = tokens(words.filter(word => word.x <= .45 && word.y >= .40));
  if (nav.length >= 3 && navigation.has('PLAY') &&
      ['PLAY', 'START', 'CANCEL'].some(token => actions.has(token)) &&
      ['NORMAL', 'CASUAL', 'RANKED', 'TRAINING'].some(token => modes.has(token))) {
    return {context: 'lobby', cues: ['top-lobby-navigation', 'bottom-left-queue-action', 'left-match-mode'], reason: 'positive-menu-evidence'};
  }

  const upper = words.filter(word => word.y <= .60);
  const lower = words.filter(word => word.y >= .65);
  const headline = ['BETTER LUCK NEXT TIME', 'WINNER WINNER CHICKEN DINNER', 'MATCH FINISHED', 'MATCH ENDED']
    .some(phrase => hasPhrase(upper, phrase));
  const summary = hasPhrase(words, 'TEAM RANK') || hasPhrase(words, 'MATCH SUMMARY') ||
    (all.has('RANK') && (all.has('KILLS') || all.has('KILLED')));
  const exit = ['RETURN TO LOBBY', 'EXIT TO LOBBY'].some(phrase => hasPhrase(lower, phrase)) || tokens(lower).has('CONTINUE');
  if (headline && summary && exit) {
    return {context: 'results', cues: ['results-headline', 'match-summary', 'bottom-results-action'], reason: 'positive-menu-evidence'};
  }
  return unknown('no-strong-menu-evidence');
}

function validImage(image) {
  return image && Number.isSafeInteger(image.width) && Number.isSafeInteger(image.height) &&
    image.width >= 128 && image.height >= 128 && Math.max(image.width, image.height) <= 2400 &&
    image.width * image.height <= 4_000_000 && ArrayBuffer.isView(image.data) &&
    image.data.BYTES_PER_ELEMENT === 1 && image.data.length === image.width * image.height * 4;
}

function footerBounds(image, supplied) {
  const bounds = supplied || {left: Math.floor(image.width * .82), top: Math.floor(image.height * .972), right: image.width, bottom: image.height};
  const {left, top, right, bottom} = bounds;
  if (![left, top, right, bottom].every(Number.isSafeInteger) || left < 0 || top < 0 ||
      right > image.width || bottom > image.height || right - left < 32 || bottom - top < 6) return null;
  return {left, top, right, bottom};
}

// Keep neutral, bright glyph edges; background colors and solid white areas do
// not count as a footer. Work is bounded to a narrow bottom-right strip.
function footerEdges(image, bounds) {
  const width = bounds.right - bounds.left, height = bounds.bottom - bounds.top;
  const mask = new Uint8Array(width * height), rgba = image.data;
  const light = (x, y) => {
    const at = (Math.max(0, Math.min(image.height - 1, y)) * image.width + Math.max(0, Math.min(image.width - 1, x))) * 4;
    return (rgba[at] + rgba[at + 1] + rgba[at + 2]) / 3;
  };
  let count = 0;
  for (let y = bounds.top; y < bounds.bottom; y++) for (let x = bounds.left; x < bounds.right; x++) {
    const at = (y * image.width + x) * 4;
    const low = Math.min(rgba[at], rgba[at + 1], rgba[at + 2]);
    const high = Math.max(rgba[at], rgba[at + 1], rgba[at + 2]);
    if (low < 110 || high - low > 80 || rgba[at + 3] < 230) continue;
    const neighbor = Math.min(light(x - 1, y), light(x + 1, y), light(x, y - 1), light(x, y + 1));
    if (light(x, y) - neighbor < 18) continue;
    mask[(y - bounds.top) * width + x - bounds.left] = 1;
    count++;
  }
  return {mask, width, height, count};
}

/** Learn only from a successfully registered live map. Keep this descriptor in
 * memory, never localStorage/IndexedDB/logs. It contains no OCR identity string.
 * The footer suffix changes during a match: ignore the rightmost 30% and match
 * only the stable left prefix. This is presence evidence, never a match ID.
 * A missed/different footer is uncertainty, never evidence that a match ended.
 */
export function createFooterDescriptor(image, {verifiedMap = false, bounds} = {}) {
  if (!verifiedMap || !validImage(image)) return null;
  const search = footerBounds(image, bounds);
  if (!search) return null;
  const found = footerEdges(image, search);
  if (found.count < 64 || found.count > found.mask.length * .38) return null;
  let left = found.width, top = found.height, right = -1, bottom = -1;
  const rows = new Set(), columns = new Set();
  for (let y = 0; y < found.height; y++) for (let x = 0; x < found.width; x++) if (found.mask[y * found.width + x]) {
    left = Math.min(left, x); top = Math.min(top, y); right = Math.max(right, x); bottom = Math.max(bottom, y);
    rows.add(y); columns.add(x);
  }
  // Reject isolated lines/icons, sparse speckle and low-detail blank strips.
  if (rows.size < 5 || columns.size < 32 || right - left < 48) return null;
  const region = {left: search.left + Math.max(0, left - 2), top: search.top + Math.max(0, top - 2),
    right: search.left + Math.min(found.width, right + 3), bottom: search.top + Math.min(found.height, bottom + 3)};
  region.right = region.left + Math.floor((region.right - region.left) * .70);
  if (region.right - region.left < 48) return null;
  const edges = footerEdges(image, region);
  const splitAt = Math.floor(edges.width / 2);
  let leftCount = 0, rightCount = 0;
  for (let i = 0; i < edges.mask.length; i++) {
    if (i % edges.width < splitAt) leftCount += edges.mask[i];
    else rightCount += edges.mask[i];
  }
  if (Math.min(leftCount, rightCount) < 24) return null;
  return Object.freeze({kind: 'match-footer-edges-v1', sourceWidth: image.width, sourceHeight: image.height,
    bounds: Object.freeze(region), width: edges.width, height: edges.height,
    mask: edges.mask, count: edges.count, splitAt, leftCount, rightCount});
}

/** Positive template support can skip OCR/veto a reset. False never means lobby,
 * exit, or a new match. Resolution changes require learning from another map.
 */
export function matchFooterDescriptor(image, descriptor) {
  const uncertain = reason => ({present: false, score: 0, reason});
  if (!validImage(image) || descriptor?.kind !== 'match-footer-edges-v1' ||
      image.width !== descriptor.sourceWidth || image.height !== descriptor.sourceHeight ||
      !(descriptor.mask instanceof Uint8Array) || descriptor.mask.length !== descriptor.width * descriptor.height ||
      !footerBounds(image, descriptor.bounds)) return uncertain('footer-unavailable');
  const current = footerEdges(image, descriptor.bounds);
  if (current.count < 64 || current.count > current.mask.length * .38) return uncertain('footer-uncertain');
  let score = 0;
  // Permit one GLOBAL pixel translation, not local dilation: dilation can make
  // different small glyphs falsely support one another. Both prefix halves must
  // independently match; dynamic suffix pixels are never compared.
  for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
    let hits = 0, leftHits = 0, rightHits = 0, currentLeftCount = 0, currentRightCount = 0;
    for (let y = 0; y < current.height; y++) for (let x = 0; x < current.width; x++) {
      const i = y * current.width + x;
      if (x < descriptor.splitAt + dx) currentLeftCount += current.mask[i];
      else currentRightCount += current.mask[i];
      const px = x + dx, py = y + dy;
      if (descriptor.mask[i] && px >= 0 && py >= 0 && px < current.width && py < current.height &&
          current.mask[py * current.width + px]) {
        hits++; if (x < descriptor.splitAt) leftHits++; else rightHits++;
      }
    }
    score = Math.max(score, Math.min(hits / descriptor.count, hits / current.count,
      leftHits / descriptor.leftCount, leftHits / Math.max(1, currentLeftCount),
      rightHits / descriptor.rightCount, rightHits / Math.max(1, currentRightCount)));
  }
  return {present: score >= .94, score, reason: score >= .94 ? 'verified-footer-match' : 'footer-uncertain'};
}

/** Require separate, consecutive, consistent positive observations before reset.
 * A map registration immediately cancels a pending non-match conclusion. Unknown
 * gameplay, inventory, pause, desktop, and elapsed time never produce shouldClear.
 */
export class NonMatchGate {
  constructor({minObservations = 3, minDurationMs = 6000, maxGapMs = 30000} = {}) {
    if (!Number.isInteger(minObservations) || minObservations < 2 ||
        !Number.isFinite(minDurationMs) || minDurationMs < 1000 ||
        !Number.isFinite(maxGapMs) || maxGapMs <= minDurationMs) throw TypeError('Invalid non-match confirmation thresholds');
    this.minObservations = minObservations;
    this.minDurationMs = minDurationMs;
    this.maxGapMs = maxGapMs;
    this.reset();
  }
  reset() {this.candidate = null; this.firstAt = null; this.lastAt = null; this.count = 0; this.confirmed = false;}
  observe(observation, now = performance.now()) {
    if (!Number.isFinite(now)) {this.reset(); return {...unknown('invalid-time'), confirmed: false, shouldClear: false, count: 0};}
    if (observation?.registeredMap || observation?.footerPresent === true) {
      this.reset(); return {context: 'match', cues: [observation.registeredMap ? 'registered-map' : 'verified-match-footer'], reason: 'positive-match-evidence', confirmed: false, shouldClear: false, count: 0};
    }
    const evidence = classifyMatchContext(observation);
    if (evidence.context === 'unknown') {this.reset(); return {...evidence, confirmed: false, shouldClear: false, count: 0};}
    if (this.candidate !== evidence.context || this.lastAt === null || now < this.lastAt || now - this.lastAt > this.maxGapMs) {
      this.reset(); this.candidate = evidence.context; this.firstAt = now;
    }
    if (this.lastAt !== now) this.count++;
    this.lastAt = now;
    const complete = this.count >= this.minObservations && now - this.firstAt >= this.minDurationMs;
    const shouldClear = complete && !this.confirmed;
    this.confirmed ||= complete;
    return {...evidence, confirmed: this.confirmed, shouldClear, count: this.count};
  }
}
