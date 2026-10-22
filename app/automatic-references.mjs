// Official public PUBG developer assets are shipped with this release.
// Sources, original names, hashes and rights are recorded in map-assets/manifest.json
// and THIRD_PARTY_NOTICES.md. No runtime GitHub or image-host request is made.
const MAX_BYTES = 2_000_000;
const DOWNLOAD_TIMEOUT_MS = 30_000;
const PNG_SIGNATURE = [137, 80, 78, 71, 13, 10, 26, 10];
const BUNDLED_REFERENCES = [
  {
    "mapId": "erangel",
    "file": "erangel.png",
    "sha256": "56bd4bf0bdcd5e902ef4c232bc54d9546ae0a6cc8b881833f45f0f0a9e93aea9",
    "width": 819,
    "height": 819
  },
  {
    "mapId": "miramar",
    "file": "miramar.png",
    "sha256": "25e47254abf6a1b339f4a030ed323f8947fcbd0628c530eba7c0973d5d45ea14",
    "width": 819,
    "height": 819
  },
  {
    "mapId": "sanhok",
    "file": "sanhok.png",
    "sha256": "184561634b90ab2e981df6edd4813f2ac6e165d5d62ed3cbe684eec079b03855",
    "width": 819,
    "height": 819
  },
  {
    "mapId": "vikendi",
    "file": "vikendi.png",
    "sha256": "a2fcd39d6ae87d82fc5747389f946e1f03ddb946ea9ac67e9944a0dcd3c05516",
    "width": 819,
    "height": 819
  },
  {
    "mapId": "karakin",
    "file": "karakin.png",
    "sha256": "87fd5c4f956a1a05858cc069fdd4da33d8ffa56d31eb9182b6038a0fbe6f216b",
    "width": 819,
    "height": 819
  },
  {
    "mapId": "paramo",
    "file": "paramo.png",
    "sha256": "dd40f9ede3225abc07421c46148f8fc76a4f87997612e68536c6c6a89c4ac4b1",
    "width": 819,
    "height": 819
  },
  {
    "mapId": "haven",
    "file": "haven.png",
    "sha256": "287435cb7b9e5f92862ac79f65c86839f9a4dcbf61c7287342caa3c85907c5fa",
    "width": 819,
    "height": 819
  },
  {
    "mapId": "taego",
    "file": "taego.png",
    "sha256": "dcf2679fa735b0b112d69783fc022b7699ee2523d6e765640b8a0b279bfe4c45",
    "width": 819,
    "height": 819
  },
  {
    "mapId": "deston",
    "file": "deston.png",
    "sha256": "be35aeb55781edd47ac547fa51b2d9c84244b55dcbc2fd621198b60aeb4da0b7",
    "width": 819,
    "height": 819
  },
  {
    "mapId": "rondo",
    "file": "rondo.png",
    "sha256": "47872f9f34bf817e37dcb7b92d2e00e054d8cc03aa0ba955eb4dd6efb17750a2",
    "width": 819,
    "height": 819
  },
  {
    "mapId": "training",
    "file": "training.png",
    "sha256": "acd5e86e095680aec13830a8e26622cba4dc787cfc675ae9b4674d569203449d",
    "width": 819,
    "height": 819
  }
];
export const AUTOMATIC_REFERENCES = Object.freeze(BUNDLED_REFERENCES.map(({file, ...record}) =>
  Object.freeze({...record, url: new URL(`./map-assets/${file}`, import.meta.url).href})));

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
    const response = await fetchImpl(pinned.url, {credentials: 'omit', cache: 'no-cache', redirect: 'error', signal: controller.signal});
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
