// Official PUBG developer assets, pinned so upstream changes require review.
// Attribution and asset terms are documented in THIRD_PARTY_NOTICES.md.
const ASSET_ROOT = 'https://raw.githubusercontent.com/pubg/api-assets/32b13b51128b8d8909ae5e77f3b833e01230b24d/Assets/Maps/';
const MAX_BYTES = 2_000_000;
const DOWNLOAD_TIMEOUT_MS = 30_000;
const PNG_SIGNATURE = [137, 80, 78, 71, 13, 10, 26, 10];

export const AUTOMATIC_REFERENCES = Object.freeze([
  Object.freeze({mapId: 'erangel', url: `${ASSET_ROOT}Erangel_Main_Low_Res.png`,
    sha256: '56bd4bf0bdcd5e902ef4c232bc54d9546ae0a6cc8b881833f45f0f0a9e93aea9', width: 819, height: 819}),
  Object.freeze({mapId: 'taego', url: `${ASSET_ROOT}Taego_Main_Low_Res.png`,
    sha256: 'dcf2679fa735b0b112d69783fc022b7699ee2523d6e765640b8a0b279bfe4c45', width: 819, height: 819}),
]);

export async function fetchReference(record, {fetchImpl = globalThis.fetch, cryptoImpl = globalThis.crypto, signal} = {}) {
  const pinned = AUTOMATIC_REFERENCES.find(item => item.mapId === record?.mapId);
  if (!pinned || pinned.url !== record.url || pinned.sha256 !== record.sha256) throw Error('Unknown automatic reference');
  if (typeof fetchImpl !== 'function' || !cryptoImpl?.subtle?.digest) throw Error('Automatic references require HTTPS and Web Crypto');

  const controller = new AbortController();
  const abort = () => controller.abort(signal.reason);
  if (signal?.aborted) abort();
  else signal?.addEventListener('abort', abort, {once: true});
  const timeout = setTimeout(() => controller.abort(Error('Automatic reference download timed out')), DOWNLOAD_TIMEOUT_MS);
  try {
    const response = await fetchImpl(pinned.url, {credentials: 'omit', cache: 'force-cache', redirect: 'error', signal: controller.signal});
    if (!response.ok) throw Error(`Automatic reference HTTP ${response.status}`);
    if (response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'image/png') throw Error('Automatic reference is not a PNG');
    if (Number(response.headers.get('content-length')) > MAX_BYTES) throw Error('Automatic reference is too large');
    if (!response.body) throw Error('Automatic reference has no content');
    const reader = response.body.getReader();
    const chunks = [];
    let count = 0;
    try {
      while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        count += value.byteLength;
        if (count > MAX_BYTES) throw Error('Automatic reference is too large');
        chunks.push(value);
      }
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    const bytes = new Uint8Array(count);
    let offset = 0;
    for (const chunk of chunks) {bytes.set(chunk, offset); offset += chunk.byteLength;}
    if (!PNG_SIGNATURE.every((byte, index) => bytes[index] === byte)) throw Error('Automatic reference is not a PNG');
    const digest = await cryptoImpl.subtle.digest('SHA-256', bytes);
    const sha256 = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
    if (sha256 !== pinned.sha256) throw Error('Automatic reference checksum mismatch');
    return new Blob([bytes], {type: 'image/png'});
  } catch (error) {
    controller.abort(error);
    throw error;
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener('abort', abort);
  }
}

// One failure must not prevent another supported map from becoming available.
// Only reviewed manifest URLs are fetched; community map metadata cannot add URLs.
export async function loadAutomaticReferences({knownMapIds, existingMapIds = [], decode, fetchImpl, cryptoImpl, signal}) {
  if (typeof decode !== 'function') throw TypeError('A reference image decoder is required');
  const known = new Set(knownMapIds), existing = new Set(existingMapIds);
  const loaded = [], failures = [];
  for (const record of AUTOMATIC_REFERENCES) {
    if (!known.has(record.mapId) || existing.has(record.mapId)) continue;
    try {
      const blob = await fetchReference(record, {fetchImpl, cryptoImpl, signal});
      loaded.push({mapId: record.mapId, image: await decode(blob)});
    } catch (error) {
      failures.push({mapId: record.mapId, error: String(error?.message || error)});
    }
  }
  return {loaded, failures};
}
