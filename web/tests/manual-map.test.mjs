import test from 'node:test';
import assert from 'node:assert/strict';
import {ManualMapSelection} from '../app/manual-map.mjs';
import {project} from '../app/session.mjs';

const map=id=>({id,name:id,points:[{id:`${id}-1`,x:.25,y:.75,kind:'tunnel_entrance'}]});
const frame=()=>({width:8,height:4,data:new Uint8ClampedArray(8*4*4)});
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return{promise,resolve,reject};};

test('a manual map projects all static locations on the full image without a capture',async()=>{
  const input=map('erangel'),image=frame(),selection=new ManualMapSelection({load:async()=>image});
  const current=await selection.select(input);
  assert.equal(selection.phase,'recognized');assert.equal(current.frame,image);
  assert.deepEqual(project(current.result.registration.matrix,.25,.75),[2,3]);
  assert.deepEqual(current.result.points,[{...input.points[0],visible:true}]);
  assert.equal(selection.controller,null);
});
test('an empty location list still opens the manual map',async()=>{
  const selection=new ManualMapSelection({load:async()=>frame()});
  assert.deepEqual((await selection.select({...map('sanhok'),points:[]})).result.points,[]);
  assert.equal(selection.phase,'recognized');
});
test('reset aborts a pending image and a late success cannot reopen the map',async()=>{
  const pending=deferred();let signal;
  const selection=new ManualMapSelection({load:(_,value)=>{signal=value;return pending.promise;}});
  const result=selection.select(map('erangel'));assert.equal(selection.phase,'loading');
  selection.reset();assert.equal(signal.aborted,true);pending.resolve(frame());
  assert.equal(await result,null);assert.equal(selection.current,null);assert.equal(selection.phase,'idle');
});
test('a newer choice wins even when the previous image completes last',async()=>{
  const old=deferred(),latest=deferred();
  const selection=new ManualMapSelection({load:m=>m.id==='erangel'?old.promise:latest.promise});
  const first=selection.select(map('erangel')),second=selection.select(map('deston'));
  latest.resolve(frame());await second;old.resolve(frame());await first;
  assert.equal(selection.current.map.id,'deston');assert.equal(selection.phase,'recognized');
});
test('stale errors do not hide the next choice and current failures can be retried',async()=>{
  const old=deferred();let fail=true;
  const selection=new ManualMapSelection({load:m=>m.id==='erangel'?old.promise:fail?Promise.reject(Error('offline')):Promise.resolve(frame())});
  const first=selection.select(map('erangel'));await selection.select(map('deston'));
  assert.equal(selection.phase,'error');fail=false;await selection.select(map('deston'));
  old.reject(Error('old failure'));await first;assert.equal(selection.phase,'recognized');
  assert.equal(selection.current.map.id,'deston');
});
test('a malformed image never produces a map or locations',async()=>{
  const selection=new ManualMapSelection({load:async()=>({...frame(),data:new Uint8ClampedArray(4)})});
  assert.equal(await selection.select(map('erangel')),null);assert.equal(selection.phase,'error');assert.equal(selection.current,null);
});
