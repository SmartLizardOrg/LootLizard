export const FEED_URL = 'https://raw.githubusercontent.com/SmartLizardOrg/LootLizard/metadata/maps.json';
const ID = /^[a-z0-9][a-z0-9_-]{0,63}$/;
export function validateMaps(maps) {
  if (!Array.isArray(maps) || maps.length > 32) throw Error('Invalid map catalog');
  const seen = new Set();
  for (const map of maps) {
    if (!map || typeof map.id !== 'string' || !ID.test(map.id) || seen.has(map.id) || typeof map.name !== 'string' || !map.name.trim() || map.name.length > 160 ||
        !Number.isFinite(map.size_m) || map.size_m < 100 || map.size_m > 100000 || !map.source || typeof map.source !== 'object' || Array.isArray(map.source) ||
        !Array.isArray(map.points) || !map.points.length || map.points.length > 5000) throw Error('Invalid map record');
    seen.add(map.id);
    const ids = new Set();
    for (const p of map.points) {
      if (!p || typeof p.id !== 'string' || !ID.test(p.id) || ids.has(p.id) || typeof p.name !== 'string' || !p.name.trim() || p.name.length > 160 ||
          !Number.isFinite(p.x) || !Number.isFinite(p.y) || p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1) throw Error('Invalid room record');
      ids.add(p.id);
    }
  }
  return maps;
}
export async function readBoundedJSON(response, maxBytes=2_000_000) {
  if (!response.ok) throw Error(`HTTP ${response.status}`);
  const declared = response.headers.get('content-length');
  if (declared && Number(declared) > maxBytes) throw Error('Map catalog is too large');
  const reader = response.body.getReader(); let count = 0; const chunks = [];
  try { while (true) { const {done,value} = await reader.read(); if (done) break; count += value.byteLength; if (count > maxBytes) throw Error('Map catalog is too large'); chunks.push(value); } }
  finally { await reader.cancel().catch(()=>{}); reader.releaseLock(); }
  const bytes = new Uint8Array(count); let offset=0; for (const value of chunks) { bytes.set(value,offset); offset += value.length; }
  return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
}
export function validateSnapshot(value) {
  if (!value || value.schema_version !== 1 || typeof value.revision !== 'string' || !value.revision.trim() || value.revision.length > 160) throw Error('Unsupported map feed');
  validateMaps(value.maps); return value;
}
