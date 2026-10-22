import {CaptureSession,project} from './session.mjs';
import {validateCatalog,readBoundedJSON} from './metadata.mjs';
import {createDemo} from './demo.mjs';
import {applyLanguage,translate} from './i18n.mjs';
import {displayMediaOptions,readCaptureSettings,applyCaptureRate,boundedFrameSize,setSamplerSize} from './capture.mjs';
import {loadAutomaticReferences} from './automatic-references.mjs';
import {browserPreferenceStorage,loadPreferences,savePreferences,SCAN_INTERVALS,nextScanDelay,captureRateForInterval} from './preferences.mjs';
import {mapViewport,sourcePreviewSize} from './map-view.mjs';
import {MatchMapMemory} from './match-memory.mjs';
import {NonMatchGate,createFooterDescriptor,matchFooterDescriptor} from './match-context.mjs';
import {createMatchContextReader} from './match-context-reader.mjs';
import {locationKind,locationLabel,locationIconSVG,presentLocationKinds,layoutLocationMarkers,drawLocationMarkers} from './location-markers.mjs';

const $=id=>document.getElementById(id);
const testing=['127.0.0.1','localhost'].includes(location.hostname)&&new URLSearchParams(location.search).get('test')==='1';
// Synthetic fixtures and processing controls have no player-facing controls.
const demo=testing?createDemo():null,session=new CaptureSession(),references=new Map();
const matchMemory=new MatchMapMemory(),nonMatchGate=new NonMatchGate(),contextReader=createMatchContextReader();
const canvas=$('map-canvas'),ctx=canvas.getContext('2d'),video=$('capture-video');
const sourcePreview=$('source-preview'),previewContext=sourcePreview.getContext('2d');
const sampler=document.createElement('canvas'),sample=sampler.getContext('2d',{willReadFrequently:true});
const worker=new Worker(new URL('./vision-worker.js',import.meta.url),{type:'module'});
let nextId=0,queue=Promise.resolve(),pending=new Map(),workerFailed=false;
let maps=[],engine=null,prepared=false,frame=null,stream=null,timer=null,scanning=false;
let phase='loading',detail='',sourceGeneration=0,connecting=false,hasSourcePreview=false,sourceRecognized=false;
let footerDescriptor=null,lastContextCheck=0,waitingForMatch=false,dimensions='',demoMode=false;
let drawnFrame=null,drawnResult=null,drawnLanguage='',lastScanAt=null,diagnosticMode='full';
const preferenceStorage=browserPreferenceStorage(window);
let {language,interval}=loadPreferences(preferenceStorage);
let captureFps=captureRateForInterval(interval),lastCaptureSettings={},lastConstraintResult=null,rateQueue=Promise.resolve();
const performanceEvents=[],t=key=>translate(key,language),put=(id,value)=>{$(id).textContent=String(value);};
const allMaps=()=>demo?[...maps,demo.map]:maps;
function recordPerformance(event){performanceEvents.push(event);if(performanceEvents.length>128)performanceEvents.shift();}
function performanceSnapshot(){return{requestedFrameRate:captureFps,settings:stream?readCaptureSettings(stream.getVideoTracks()[0]):lastCaptureSettings,mode:diagnosticMode,active:!!stream,events:performanceEvents.slice()};}
function request(type,payload={},transfer=[]){
  const run=()=>new Promise((resolve,reject)=>{
    if(workerFailed){reject(Error('Recognition unavailable'));return;}
    const id=++nextId,timeout=setTimeout(()=>{
      pending.delete(id);workerFailed=true;worker.terminate();
      for(const item of pending.values()){clearTimeout(item.timeout);item.reject(Error('Recognition unavailable'));}
      pending.clear();stop();status('error','LootLizard stopped responding. Refresh this page to try again.');reject(Error('Recognition unavailable'));
    },type==='init'?240000:60000);
    pending.set(id,{resolve,reject,timeout});worker.postMessage({id,type,...payload},transfer);
  });
  const result=queue.then(run);queue=result.catch(()=>{});return result;
}
worker.onmessage=({data})=>{
  if(data.type==='progress')return;
  const item=pending.get(data.id);if(!item)return;pending.delete(data.id);clearTimeout(item.timeout);
  data.type==='error'?item.reject(Error(data.reason)):item.resolve(data);
};
worker.onerror=()=>{
  workerFailed=true;for(const item of pending.values()){clearTimeout(item.timeout);item.reject(Error('Recognition unavailable'));}pending.clear();
  stop();status('error','LootLizard stopped responding. Refresh this page to try again.');
};
function displayResult(){return matchMemory.current?.result||null;}
function currentMap(){return allMaps().find(map=>map.id===displayResult()?.registration?.mapId)||null;}
function targets(){
  const map=currentMap(),result=displayResult();if(!map)return[];
  const visible=new Map((result.points||[]).map(point=>[point.id,point]));
  return [...map.points].sort((a,b)=>a.id.localeCompare(b.id)).map(point=>({...point,...visible.get(point.id)}));
}
function clearGuidance(){session.invalidate();matchMemory.reset();nonMatchGate.reset();contextReader.terminate();footerDescriptor=null;lastContextCheck=0;waitingForMatch=false;render();}
function resetMatch(){clearGuidance();waitingForMatch=true;status('unknown','Ready for your next match. Open the map in game.');schedule();}
function status(next,message=''){phase=next;detail=message;render();}
function updateAge(){
  const snapshot=matchMemory.current;
  put('snapshot-age',snapshot?`${Math.max(0,Math.floor((Date.now()-snapshot.mapUpdatedAt)/1000))} s ${t('ago')}`:t('No map yet'));
}
function renderStage(map){
  const connected=!!stream,snapshot=matchMemory.current;
  const viewport=snapshot?mapViewport(snapshot.result.registration.matrix,snapshot.frame.width,snapshot.frame.height):null;
  const view=map&&viewport?'map':phase==='error'?'error':connecting?'connecting':connected?'waiting':'setup';
  $('map-stage').dataset.view=view;canvas.hidden=view!=='map';$('canvas-empty').hidden=!canvas.hidden;
  $('setup-steps').hidden=view!=='setup';$('stage-hint').hidden=view!=='setup';
  $('connect-source').hidden=connected||connecting||view==='map';$('connect-source').disabled=$('start-sharing').disabled;
  $('retained-banner').hidden=view!=='map'||phase==='recognized';$('reset-match').disabled=!snapshot;
  const messages={
    setup:['Start PUBG','Start PUBG, then connect its window.'],
    connecting:['Choose your PUBG window','Select the PUBG window or the monitor showing the game in the browser picker.'],
    waiting:['Open the map for automatic recognition','Keep playing. LootLizard checks for the map automatically.'],
    error:['Map recognition unavailable',detail||'Refresh this page to try again.'],
  };
  const [title,message]=view==='waiting'&&waitingForMatch?['Waiting for a new match','Ready for your next match. Open the map in game.']:messages[view]||messages.waiting;
  put('stage-title',t(title));put('stage-detail',t(message));$('source-panel').hidden=!connected;
  put('source-status',t(stream?.getVideoTracks()[0]?.muted?'Sharing is paused.':hasSourcePreview?'Your connected PUBG source':'Waiting for your game…'));
}
function render(){
  const map=currentMap(),points=targets();
  const names={loading:'Preparing LootLizard…',idle:'Ready when you are',scanning:'Looking for the map…',recognized:'Map found',unknown:'Open your map',stopped:'Sharing stopped',error:'Something went wrong'};
  const retained=!!map&&phase!=='recognized';
  put('recognition-status',t(retained?'Map saved':names[phase]||phase));
  put('recognition-detail',t(retained?'Your map stays here while you play. Open it in game to refresh.':detail||'Connect PUBG, then open the full map in game.'));
  $('recognition-indicator').className=`status-indicator ${map?'is-ready':phase==='error'?'is-error':phase==='scanning'?'is-warning':''}`;
  put('map-name',map?.name||t('Waiting for a map'));put('room-count',points.length);
  put('capture-status',t(stream?'Connected':'Not sharing'));
  put('last-update',matchMemory.current?new Date(matchMemory.current.mapUpdatedAt).toLocaleTimeString(language==='hu'?'hu-HU':'en-GB'):'—');updateAge();
  $('start-sharing').disabled=!prepared||workerFailed||connecting||!!stream;
  $('stop-sharing').disabled=!session.active&&!stream&&!connecting;renderStage(map);
  $('empty-targets').hidden=!!points.length;
  $('paramo-note').hidden=map?.id!=='paramo';
  $('haven-note').hidden=map?.id!=='haven'||!points.length;
  const legend=presentLocationKinds(points).map(kind=>{
    const item=document.createElement('li'),icon=document.createElement('span'),label=document.createElement('span');
    icon.className='location-icon';icon.innerHTML=locationIconSVG(kind);label.textContent=t(locationLabel(kind));item.append(icon,label);return item;
  });$('location-legend').replaceChildren(...legend);$('location-legend').hidden=!legend.length;
  const empty=$('empty-targets').querySelector('p');if(empty)empty.textContent=t(map?'No locations listed for this map yet.':'Locations appear here when your map is recognized.');
  const rows=points.map((point,index)=>{
    const row=document.createElement('tr'),rank=document.createElement('td'),cell=document.createElement('td'),icon=document.createElement('span'),name=document.createElement('span');
    rank.textContent=String(index+1);icon.className='location-icon';icon.innerHTML=locationIconSVG(locationKind(point));icon.setAttribute('role','img');icon.setAttribute('aria-label',t(locationLabel(locationKind(point))));
    name.textContent=point.name;cell.className='location-cell';cell.append(icon,name);row.append(rank,cell);return row;
  });$('target-list').replaceChildren(...rows);draw(points);
}
function draw(points=targets(),force=false){
  const overlay=displayResult(),mapFrame=matchMemory.current?.frame;
  if(!force&&drawnFrame===mapFrame&&drawnResult===overlay&&drawnLanguage===language)return;
  drawnFrame=mapFrame;drawnResult=overlay;drawnLanguage=language;
  const viewport=mapFrame&&overlay?mapViewport(overlay.registration.matrix,mapFrame.width,mapFrame.height):null;
  if(!viewport){setSamplerSize(canvas,1,1);ctx.clearRect(0,0,1,1);return;}
  setSamplerSize(canvas,viewport.width,viewport.height);
  ctx.putImageData(mapFrame,-viewport.x,-viewport.y,viewport.x,viewport.y,viewport.width,viewport.height);
  const box=canvas.getBoundingClientRect(),unit=1/Math.max(.05,Math.min(box.width/canvas.width,box.height/canvas.height));
  const projectedPoints=points.flatMap((point,index)=>{
    if(!point.visible)return[];const projected=project(overlay.registration.matrix,point.x,point.y);if(!projected)return[];
    return[{id:point.id,index:index+1,kind:locationKind(point),x:(projected[0]-viewport.x)/unit,y:(projected[1]-viewport.y)/unit}];
  });
  ctx.save();ctx.scale(unit,unit);drawLocationMarkers(ctx,layoutLocationMarkers(projectedPoints,canvas.width/unit,canvas.height/unit));ctx.restore();
}
function updatePreview(image,{sampled=false}={}){
  if(!image||!$('source-details').open)return;
  const size=sourcePreviewSize(image.width,image.height);setSamplerSize(sourcePreview,size.width,size.height);
  // Reuse the sampler when its pixels are current; a disclosure toggle may
  // instead need the most recent owned frame after its buffer was transferred.
  if(!sampled){setSamplerSize(sampler,image.width,image.height);sample.putImageData(image,0,0);}
  previewContext.drawImage(sampler,0,0,sourcePreview.width,sourcePreview.height);hasSourcePreview=true;
}
function stop(){
  sourceGeneration++;clearTimeout(timer);timer=null;session.stop();
  matchMemory.reset();nonMatchGate.reset();contextReader.terminate();footerDescriptor=null;lastContextCheck=0;waitingForMatch=false;
  if(stream)lastCaptureSettings=readCaptureSettings(stream.getVideoTracks()[0]);
  const old=stream;stream=null;if(old)old.getTracks().forEach(track=>track.stop());video.srcObject=null;
  demoMode=false;connecting=false;hasSourcePreview=false;sourceRecognized=false;frame=null;lastScanAt=null;
  $('source-details').open=true;previewContext.clearRect(0,0,sourcePreview.width,sourcePreview.height);
  dimensions='';phase='stopped';detail='';render();
}
function schedule(){clearTimeout(timer);timer=null;if(session.active&&session.source==='screen'&&!scanning)timer=setTimeout(scanScreen,nextScanDelay(interval,lastScanAt,performance.now()));}
function capture(){
  if(!video.videoWidth||!video.videoHeight||video.readyState<2)return null;
  const native=`${video.videoWidth}x${video.videoHeight}`;
  if(dimensions&&native!==dimensions){session.invalidate();footerDescriptor=null;nonMatchGate.reset();contextReader.terminate();lastContextCheck=0;}dimensions=native;
  const size=boundedFrameSize(video.videoWidth,video.videoHeight);setSamplerSize(sampler,size.width,size.height);sample.drawImage(video,0,0,sampler.width,sampler.height);
  const image=sample.getImageData(0,0,sampler.width,sampler.height);updatePreview(image,{sampled:true});return image;
}
async function analyze(image,{owned=false,captureMetrics={}}={}){
  const ticket=session.issue();if(!ticket)return null;
  const started=performance.now(),metrics={type:'scan',epochMs:performance.timeOrigin+started,...captureMetrics,width:image.width,height:image.height};
  session.result=null;frame=owned?image:new ImageData(new Uint8ClampedArray(image.data),image.width,image.height);
  metrics.retainMs=performance.now()-started;let stage=performance.now();status('scanning');metrics.initialRenderMs=performance.now()-stage;
  if(session.source==='screen'&&!demoMode&&!references.size){
    const result={width:image.width,height:image.height,registration:null,position:null,zone:null,points:[],reason:'Map images are unavailable. Refresh this page to try again.'};
    if(!session.accept(ticket,result))return null;status('unknown',result.reason);
    Object.assign(metrics,{path:'no-references',totalMs:performance.now()-started});recordPerformance(metrics);return result;
  }
  stage=performance.now();const buffer=new Uint8Array(image.data).buffer;metrics.transferCopyMs=performance.now()-stage;
  try{
    stage=performance.now();const result=await request('analyze',{rgba:buffer,width:image.width,height:image.height,context:'map-only',mapId:currentMap()?.id||null,ticket},[buffer]);metrics.workerRoundTripMs=performance.now()-stage;
    if(!session.accept(ticket,result))return null;
    if(result.registration){
      matchMemory.update(result,frame,metrics.captureEpochMs||metrics.epochMs);waitingForMatch=false;nonMatchGate.observe({registeredMap:true});
      if(session.source==='screen'){
        if(!sourceRecognized){sourceRecognized=true;$('source-details').open=false;}
        if(!demoMode)footerDescriptor=createFooterDescriptor(frame,{verifiedMap:true});
      }
    }
    stage=performance.now();status(result.registration?'recognized':'unknown',result.registration?'Small markers show the listed locations.':'Open the full map in game.');
    if(!result.registration)await checkMatchContext(frame,ticket);
    Object.assign(metrics,{path:'worker',python:result.timings,resultRenderMs:performance.now()-stage,totalMs:performance.now()-started});recordPerformance(metrics);return result;
  }catch(error){if(session.accepts(ticket)){session.accept(ticket,null);status('error','Could not read the map. Keep it open and try again.');}throw error;}
}
async function checkMatchContext(image,ticket){
  if(session.source!=='screen'||demoMode||!matchMemory.current)return;
  if(matchFooterDescriptor(image,footerDescriptor).present){nonMatchGate.observe({footerPresent:true});return;}
  const now=performance.now(),delay=nonMatchGate.count?6000:12000;if(lastContextCheck&&now-lastContextCheck<delay)return;
  lastContextCheck=now;const generation=sourceGeneration,started=performance.now();
  if(!contextReader.getState().ready){
    const epoch=session.epoch;contextReader.prepare().then(ready=>{
      if(generation!==sourceGeneration||epoch!==session.epoch||!matchMemory.current)return;
      recordPerformance({type:'match-context-startup',epochMs:Date.now(),durationMs:performance.now()-started,status:ready?'ready':'unavailable'});
    });return;
  }
  const observation=await contextReader.read(image);
  if(generation!==sourceGeneration||!session.active||session.epoch!==ticket.epoch||session.sequence!==ticket.sequence||!matchMemory.current)return;
  const evidence=nonMatchGate.observe(observation);recordPerformance({type:'match-context',epochMs:Date.now(),durationMs:performance.now()-started,status:observation.status,context:evidence.context});
  if(evidence.shouldClear)resetMatch();
}
async function scanScreen(){
  if(!session.active||session.source!=='screen'||scanning)return;
  const track=stream?.getVideoTracks()[0];if(!track||track.readyState!=='live'){stop();return;}
  lastScanAt=performance.now();
  if(track.muted){session.invalidate();status('unknown','Sharing is paused.');schedule();return;}
  if(testing&&diagnosticMode==='capture-only'){schedule();return;}
  scanning=true;try{
    const start=performance.now(),image=capture(),captureMs=performance.now()-start;
    if(image){
      if(testing&&diagnosticMode==='preview-only'){clearGuidance();frame=image;status('idle');recordPerformance({type:'scan',path:'preview-only',epochMs:performance.timeOrigin+start,captureMs,width:image.width,height:image.height});}
      else await analyze(image,{owned:true,captureMetrics:{captureEpochMs:performance.timeOrigin+start,captureMs}});
    }else{session.invalidate();status('unknown','Waiting for your game…');}
  }catch{}finally{scanning=false;schedule();}
}
async function setWorkerReferences(useDemo=demoMode){
  const records=useDemo?[{mapId:'demo',image:demo.reference}]:[...references].map(([mapId,record])=>({mapId,image:record.image}));
  const transfer=[],payload=records.map(({mapId,image})=>{const rgba=new Uint8Array(image.data).buffer;transfer.push(rgba);return{mapId,rgba,width:image.width,height:image.height};});
  return request('references',{references:payload},transfer);
}
async function attachStream(media,token,useDemo=false){
  if(token!==sourceGeneration){media.getTracks().forEach(track=>track.stop());return;}
  stream=media;video.srcObject=media;const track=media.getVideoTracks()[0];if(!track){stop();throw Error('No video track selected');}
  lastConstraintResult=null;lastCaptureSettings=readCaptureSettings(track);recordPerformance({type:'capture-start',epochMs:Date.now(),requestedFrameRate:captureFps,settings:lastCaptureSettings});
  track.addEventListener('ended',()=>{if(stream===media)stop();});
  track.addEventListener('mute',()=>{if(stream===media){session.invalidate();nonMatchGate.reset();contextReader.terminate();status('unknown','Sharing is paused.');}});
  track.addEventListener('unmute',()=>{if(stream===media){lastContextCheck=0;schedule();}});
  try{
    await video.play();await setWorkerReferences(useDemo);if(token!==sourceGeneration||track.readyState!=='live')return;
    connecting=false;session.begin('screen');demoMode=useDemo;status('unknown','Open the full map in game.');scanScreen();
  }catch(error){if(stream===media)stop();throw error;}
}
function startSharing(){
  stop();const token=sourceGeneration;
  if(!navigator.mediaDevices?.getDisplayMedia){status('error','Screen sharing needs a supported desktop browser.');return;}
  connecting=true;let picked;
  try{picked=navigator.mediaDevices.getDisplayMedia(displayMediaOptions(captureFps));}
  catch{connecting=false;status('error','Could not connect. Choose your PUBG window and try again.');return;}
  status('idle','Select the PUBG window or the monitor showing the game in the browser picker.');
  picked.then(media=>attachStream(media,token)).catch(()=>{if(token===sourceGeneration){connecting=false;status('idle','Choose your PUBG window when you are ready.');}});
}
async function decodeImage(blob){
  const image=await createImageBitmap(blob);
  try{
    if(image.width*image.height>40000000||Math.max(image.width,image.height)>8192)throw Error('Invalid map image');
    const size=boundedFrameSize(image.width,image.height,1800),copy=document.createElement('canvas');copy.width=size.width;copy.height=size.height;
    const context=copy.getContext('2d',{willReadFrequently:true});context.fillStyle='#000';context.fillRect(0,0,copy.width,copy.height);context.drawImage(image,0,0,copy.width,copy.height);return context.getImageData(0,0,copy.width,copy.height);
  }finally{image.close();}
}
function changeInterval(value){
  if(!SCAN_INTERVALS.includes(value))return;interval=value;captureFps=captureRateForInterval(interval);savePreferences(preferenceStorage,{language,interval});schedule();
  const token=sourceGeneration,track=stream?.getVideoTracks()[0],requestedFps=captureFps;
  rateQueue=rateQueue.catch(()=>{}).then(async()=>{
    if(!track||token!==sourceGeneration||requestedFps!==captureFps)return;
    const result=await applyCaptureRate(track,requestedFps);if(token!==sourceGeneration||track!==stream?.getVideoTracks()[0])return;
    lastConstraintResult=result;lastCaptureSettings=result.settings;recordPerformance({type:'capture-rate',epochMs:Date.now(),requestedFrameRate:requestedFps,result});
  });
}
$('start-sharing').addEventListener('click',startSharing);$('connect-source').addEventListener('click',startSharing);$('stop-sharing').addEventListener('click',stop);$('reset-match').addEventListener('click',resetMatch);
$('source-details').addEventListener('toggle',()=>{if($('source-details').open&&stream)updatePreview(frame);});
$('language-select').value=language;$('scan-interval').value=String(interval);
$('language-select').addEventListener('change',()=>{language=$('language-select').value==='hu'?'hu':'en';applyLanguage(language);savePreferences(preferenceStorage,{language,interval});render();});
$('scan-interval').addEventListener('change',()=>changeInterval(Number($('scan-interval').value)));
window.addEventListener('pagehide',stop);new ResizeObserver(()=>draw(undefined,true)).observe($('map-stage'));setInterval(updateAge,1000);

const ready=(async()=>{
  applyLanguage(language);render();
  const catalog=validateCatalog(await readBoundedJSON(await fetch('../data/maps.json')));maps=catalog.maps;
  const response=await request('init',{maps:allMaps()});engine=response.capabilities;
  const result=await loadAutomaticReferences({knownMapIds:maps.map(map=>map.id),existingMapIds:[],decode:decodeImage});
  for(const record of result.loaded)references.set(record.mapId,{image:record.image});
  if(result.failures.length||references.size!==maps.length)throw Error('Incomplete bundled maps');
  await setWorkerReferences(false);prepared=true;status('idle','Connect PUBG, then open the full map in game.');return response;
})();
ready.catch(()=>status('error','Could not prepare LootLizard. Refresh this page to try again.'));

if(testing){
  async function analyzeImageData(image,{source='image'}={}){
    stop();const token=sourceGeneration;await ready;if(token!==sourceGeneration)return null;demoMode=source==='demo';
    await setWorkerReferences(demoMode);if(token!==sourceGeneration)return null;session.begin(source);return analyze(image);
  }
  window.lootLizard=Object.freeze({ready,demo:()=>analyzeImageData(demo.mapFrame,{source:'demo'}),analyzeImageData,stop,
    getState:()=>({...session.snapshot(),phase,mapId:currentMap()?.id||null,points:targets(),position:null,zone:null,mapUpdatedAt:matchMemory.current?.mapUpdatedAt||null,positionUpdatedAt:null,zoneUpdatedAt:null,referenceCount:references.size,interval,engine}),
    getPerformance:performanceSnapshot,
    configureTestProcessing:mode=>{if(!['full','capture-only','preview-only'].includes(mode))throw Error('Invalid mode');diagnosticMode=mode;clearGuidance();status('idle');schedule();},
    startTestStream:async(media,{demo:synthetic=false,withoutReferences=false}={})=>{stop();const token=sourceGeneration;await ready;if(withoutReferences){references.clear();await request('references',{references:[]});}await attachStream(media,token,synthetic);},
  });
}
