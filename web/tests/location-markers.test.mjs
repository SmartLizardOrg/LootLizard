import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {LOCATION_KINDS,locationKind,locationLabel,locationIconSVG,presentLocationKinds,layoutLocationMarkers,drawLocationMarkers} from '../app/location-markers.mjs';
import {translate} from '../app/i18n.mjs';

const overlaps = (a,b) => a.x < b.x+b.width && a.x+a.width > b.x && a.y < b.y+b.height && a.y+a.height > b.y;
test('all five location types have distinct vector symbols and translated accessible labels', () => {
  assert.deepEqual(LOCATION_KINDS, ['secret_room','security_room','bear_cave','tunnel_entrance','supply_cache']);
  const symbols = LOCATION_KINDS.map(locationIconSVG);
  assert.equal(new Set(symbols.map(svg=>svg.match(/<path d="([^"]+)"/)[1])).size,LOCATION_KINDS.length);
  for(const kind of LOCATION_KINDS){
    assert.match(locationIconSVG(kind), /<svg viewBox="0 0 24 24"/);
    assert.doesNotMatch(locationIconSVG(kind), /<image|<script|href=|https?:|data:/);
    assert.notEqual(translate(locationLabel(kind),'hu'), locationLabel(kind));
  }
  assert.equal(locationKind({}), 'secret_room');
  assert.equal(locationIconSVG(locationKind({})),locationIconSVG('secret_room'));
  assert.deepEqual(presentLocationKinds([{kind:'bear_cave'},{}, {kind:'bear_cave'}]),['secret_room','bear_cave']);
  assert.deepEqual(presentLocationKinds([]),[]);
});

test('crowded locations keep every exact anchor while moving or omitting only badges', () => {
  const points=Array.from({length:60},(_,index)=>({id:`point-${index}`,index:index+1,kind:LOCATION_KINDS[index%LOCATION_KINDS.length],x:150+(index%3),y:150+(index%2)}));
  const layout=layoutLocationMarkers(points,320,320),badges=layout.filter(item=>item.badge);
  assert.equal(layout.length,points.length);
  assert.ok(badges.length>0 && badges.length<points.length, 'Unplaceable labels must not cover exact locations');
  layout.forEach((item,index)=>{
    assert.deepEqual(item.anchor,{x:points[index].x,y:points[index].y});
    assert.equal(item.id,points[index].id);assert.equal(item.index,points[index].index);
    if(item.badge)assert.ok(Math.hypot(item.leader.x-item.anchor.x,item.leader.y-item.anchor.y)<=48);
  });
  for(let a=0;a<badges.length;a++)for(let b=a+1;b<badges.length;b++)assert.equal(overlaps(badges[a].badge,badges[b].badge),false);
  for(const item of badges)for(const point of points)assert.equal(overlaps(item.badge,{x:point.x-4,y:point.y-4,width:8,height:8}),false);
  assert.deepEqual(layoutLocationMarkers(points,320,320),layout, 'Placement must remain stable between redraws');
});

test('edge badges stay inside the map without clamping or relocating source coordinates', () => {
  const points=[[0,0],[200,0],[0,160],[200,160]].map(([x,y],index)=>({id:String(index),index:index+1,x,y}));
  const layout=layoutLocationMarkers(points,200,160);
  assert.equal(layout.length,4);
  layout.forEach((item,index)=>{
    assert.deepEqual(item.anchor,{x:points[index].x,y:points[index].y});
    assert.ok(item.badge);
    assert.ok(item.badge.x>=1 && item.badge.y>=1);
    assert.ok(item.badge.x+item.badge.width<=199 && item.badge.y+item.badge.height<=159);
  });
  assert.deepEqual(layoutLocationMarkers(points,0,160),[]);
  assert.deepEqual(layoutLocationMarkers([{x:NaN,y:20},{x:-1,y:20},{x:201,y:20}],200,160),[]);
});

test('canvas renders the small exact anchors after all offset badges', () => {
  const calls=[],previous=globalThis.Path2D;
  globalThis.Path2D=class {constructor(path){this.path=path;}};
  const ctx=new Proxy({}, {get:(_,name)=>(...args)=>calls.push([name,...args]),set:()=>true});
  try {
    const layout=layoutLocationMarkers(LOCATION_KINDS.map((kind,index)=>({kind,index:index+1,x:60+index*100,y:100})),540,200);
    drawLocationMarkers(ctx,layout);
    const arcs=calls.filter(([name])=>name==='arc');
    assert.deepEqual(arcs.map(([,x,y])=>[x,y]),layout.map(item=>[item.anchor.x,item.anchor.y]));
    assert.ok(arcs.every(([,x,y,radius])=>radius===2.2));
    assert.equal(calls.filter(([name,...args])=>name==='stroke' && args[0] instanceof Path2D).length,LOCATION_KINDS.length);
    assert.ok(calls.findIndex(([name])=>name==='arc')>calls.findLastIndex(([name])=>name==='strokeRect'));
  } finally {if(previous===undefined)delete globalThis.Path2D;else globalThis.Path2D=previous;}
});

test('app shares vector icons between map, list and present-type legend, with map-specific uncertainty notes', () => {
  const html=readFileSync(new URL('../app/index.html',import.meta.url),'utf8');
  const app=readFileSync(new URL('../app/app.js',import.meta.url),'utf8');
  assert.match(html,/id="location-legend"[^>]*aria-label="Location symbols"/);
  assert.match(app,/presentLocationKinds\(points\)/);
  assert.match(app,/icon\.setAttribute\('aria-label',t\(locationLabel\(locationKind\(point\)\)\)\)/);
  assert.match(app,/\$\('paramo-note'\)\.hidden=map\?\.id!=='paramo'/);
  assert.match(html,/id="paramo-note"[^>]*hidden/);
  assert.match(app,/\$\('haven-note'\)\.hidden=map\?\.id!=='haven'\|\|!points\.length/);
  assert.match(html,/id="haven-note"[^>]*hidden/);
  assert.notEqual(translate('Paramo landmarks can change between matches. Check these locations on your current map.','hu'),'Paramo landmarks can change between matches. Check these locations on your current map.');
  const havenNote='Possible Pillar cache buildings. Only some are active each match; this historical list needs checking.';
  assert.notEqual(translate(havenNote,'hu'),havenNote);
});
