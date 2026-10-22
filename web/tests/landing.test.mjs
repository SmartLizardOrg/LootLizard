import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, readdirSync, existsSync} from 'node:fs';

const directory = new URL('../landing/', import.meta.url);
const html = readFileSync(new URL('index.html', directory), 'utf8');
const text = html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ');

test('every launch CTA opens the app directly and the landing needs no script', () => {
  const launches = [...html.matchAll(/<a\b([^>]+)>Open LootLizard\b/g)];
  assert.equal(launches.length, 3);
  for (const [, attributes] of launches) assert.match(attributes, /href="\/app\/"/);
  assert.doesNotMatch(html, /<script\b|<button\b/);
  for (const [, asset] of html.matchAll(/(?:href|src)="\.\/([^"#]+)"/g)) {
    assert.equal(existsSync(new URL(asset, directory)), true, `Missing local landing asset: ${asset}`);
  }
});

test('the illustration shows fixed location anchors without unsupported player or circle features', () => {
  assert.equal([...html.matchAll(/class="room-anchor"/g)].length, 6);
  assert.doesNotMatch(html, /player-marker|show-inside|show-all|outside-anchor|inside-anchor/);
  assert.doesNotMatch(text, /inside (?:the )?circle|position estimate|distance|synthetic demo|add a newer reference|import.*reference/i);
  assert.match(text, /Original schematic · not game data/);
  assert.match(text, /every second by default/);
  assert.match(text, /half a second to ten seconds/);
  assert.match(text, /Your last map stays visible while you play/);
});

test('map and location availability claims match the bundled source catalog', () => {
  const dataDirectory = new URL('../../data/', import.meta.url);
  const maps = readdirSync(dataDirectory).filter(name => name.endsWith('.json'))
    .map(name => JSON.parse(readFileSync(new URL(name, dataDirectory), 'utf8')))
    .filter(map => typeof map.id === 'string' && Array.isArray(map.points));
  assert.match(text, new RegExp(`${maps.length} bundled maps`));
  assert.match(text, /including Training/);
  const mapsWithPoints = maps.filter(map => map.points.length);
  const mapTags = [...html.matchAll(/<span\b[^>]*\bdata-map-id="([^"]+)"[^>]*>([^<]+)<\/span>/g)];
  assert.deepEqual(mapTags.map(([, id]) => id).sort(), mapsWithPoints.map(map => map.id).sort());
  for (const [, id, label] of mapTags) {
    assert.equal(label, mapsWithPoints.find(map => map.id === id).name.toUpperCase());
  }
  assert.match(text, new RegExp(`Hidden-loot locations on ${mapsWithPoints.length} maps`));
  assert.match(text, /Community coordinates · verify in game/);
  assert.match(text, /lists may be incomplete or out of date/);
  assert.match(text, /Paramo landmarks can change between matches/);
  assert.match(text, /check its locations on your current map/);
  assert.match(text, /Haven markers show historical possible Pillar cache buildings/);
  assert.match(text, /Only some are active each match/);
  assert.match(text, /Built for desktop Chrome and Edge/);
});
