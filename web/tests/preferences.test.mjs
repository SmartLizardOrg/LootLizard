import test from 'node:test';
import assert from 'node:assert/strict';
import {PREFERENCES_KEY,SCAN_INTERVALS,browserPreferenceStorage,loadPreferences,savePreferences,nextScanDelay,captureRateForInterval} from '../app/preferences.mjs';

test('new, old and damaged preferences default to one second without losing a valid language',()=>{
  for(const value of [null,'{','{}',JSON.stringify({interval:3000}),JSON.stringify({interval:'500'})]){
    assert.deepEqual(loadPreferences({getItem:()=>value}),{language:'en',interval:1000});
  }
  assert.deepEqual(loadPreferences({getItem:()=>JSON.stringify({language:'hu',interval:1500})}),{language:'hu',interval:1000});
});

test('all five intervals round trip together with language in the same browser preference',()=>{
  assert.deepEqual(SCAN_INTERVALS,[500,1000,2000,5000,10000]);
  const entries=new Map(),storage={setItem:(key,value)=>entries.set(key,value),getItem:key=>entries.get(key)};
  for(const interval of SCAN_INTERVALS){
    assert.equal(savePreferences(storage,{language:'hu',interval}),true);
    assert.deepEqual(loadPreferences(storage),{language:'hu',interval});
    assert.deepEqual([...entries.keys()],[PREFERENCES_KEY]);
  }
});

test('unavailable storage does not prevent setup or changing preferences',()=>{
  const storage={getItem:()=>{throw Error('blocked');},setItem:()=>{throw Error('full');}};
  assert.deepEqual(loadPreferences(storage),{language:'en',interval:1000});
  assert.equal(savePreferences(storage,{language:'hu',interval:5000}),false);
  const denied=browserPreferenceStorage({get localStorage(){throw Error('SecurityError');}});
  assert.equal(denied,null);
  assert.deepEqual(loadPreferences(denied),{language:'en',interval:1000});
  assert.equal(savePreferences(denied,{language:'hu',interval:5000}),false);
});

test('start-to-start cadence accounts for processing and never accumulates overdue frames',()=>{
  assert.equal(nextScanDelay(1000,null,100),0);
  assert.equal(nextScanDelay(1000,100,350),750);
  assert.equal(nextScanDelay(1000,100,1100),0);
  assert.equal(nextScanDelay(1000,100,5100),0);
  assert.equal(nextScanDelay(1000,100,50),1000);
  for(const interval of SCAN_INTERVALS)assert.equal(captureRateForInterval(interval),1000/interval);
  assert.throws(()=>nextScanDelay(3000,100,200),RangeError);
  assert.throws(()=>captureRateForInterval(3000),RangeError);
});
