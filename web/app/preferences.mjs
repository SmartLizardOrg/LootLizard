/** Player preferences are local to this browser; map data belongs to the release. */
export const PREFERENCES_KEY = 'lootlizard.web.preferences.v1';
export const SCAN_INTERVALS = Object.freeze([500, 1000, 2000, 5000, 10000]);
export const DEFAULT_INTERVAL = 1000;

export function browserPreferenceStorage(browser) {
  try { return browser.localStorage; }
  catch { return null; }
}

export function normalizePreferences(value) {
  return {language: value?.language === 'hu' ? 'hu' : 'en',
    interval: SCAN_INTERVALS.includes(value?.interval) ? value.interval : DEFAULT_INTERVAL};
}

export function loadPreferences(storage) {
  try { return normalizePreferences(JSON.parse(storage.getItem(PREFERENCES_KEY))); }
  catch { return normalizePreferences(null); }
}

export function savePreferences(storage, value) {
  try { storage.setItem(PREFERENCES_KEY, JSON.stringify(normalizePreferences(value))); return true; }
  catch { return false; }
}

/** Start-to-start cadence with one in-flight scan: slow work never queues frames. */
export function nextScanDelay(interval, startedAt, now) {
  if (!SCAN_INTERVALS.includes(interval)) throw new RangeError('Unsupported check interval');
  return startedAt === null ? 0 : Math.max(0, interval - Math.max(0, now - startedAt));
}

export function captureRateForInterval(interval) {
  if (!SCAN_INTERVALS.includes(interval)) throw new RangeError('Unsupported check interval');
  return 1000 / interval;
}
