import {CaptureSession, project, orderTargets} from './session.mjs';
import {FEED_URL,validateMaps,validateSnapshot,readBoundedJSON} from './metadata.mjs';
import {createDemo} from './demo.mjs';
import {referenceStore} from './storage.mjs';
import {applyLanguage,translate} from './i18n.mjs';
import {displayMediaOptions,readCaptureSettings,applyCaptureRate,boundedFrameSize,setSamplerSize} from './capture.mjs';
import {loadAutomaticReferences} from './automatic-references.mjs';
import {mapViewport,sourcePreviewSize} from './map-view.mjs';
import {MatchMapMemory} from './match-memory.mjs';
import {NonMatchGate,createFooterDescriptor,matchFooterDescriptor} from './match-context.mjs';
import {createMatchContextReader} from './match-context-reader.mjs';

const $=id=>document.getElementById(id);
const session=new CaptureSession(), demo=createDemo(), references=new Map();
const matchMemory=new MatchMapMemory(),nonMatchGate=new NonMatchGate(),contextReader=createMatchContextReader();
let footerDescriptor=null,lastContextCheck=0,contextUnavailable=false,waitingForMatch=false;
const canvas=$('map-canvas'),ctx=canvas.getContext('2d'),video=$('capture-video');
const sourcePreview=$('source-preview'),previewContext=sourcePreview.getContext('2d');
const sampler=document.createElement('canvas'),sample=sampler.getContext('2d',{willReadFrequently:true});
const worker=new Worker(new URL('./vision-worker.js',import.meta.url),{type:'module'});
let nextId=0,queue=Promise.resolve(),pending=new Map(),workerFailed=false;
let maps=[],engine=null,frame=null,stream=null,timer=null,scanning=false,configuring=0;
let phase='loading',detail='',language='en',interval=3000,remember=true,revision='bundled';
let metadataKey='Using bundled coordinates';
let crop=null,selection=null,demoMode=false,dimensions='',sourceGeneration=0;
let drawnFrame=null,drawnResult=null,drawnSelection=null,drawnCrop=null,drawnLanguage='',captureFps=1,diagnosticMode='full';
const diagnosticsEnabled=['127.0.0.1','localhost'].includes(location.hostname)&&new URLSearchParams(location.search).get('diagnostics')==='1';
const performanceEvents=[];
let lastCaptureSettings={},lastConstraintResult=null;
let referenceWarning='';
let connecting=false,hasSourcePreview=false;
const PREFS='lootlizard.web.preferences.v1',CATALOG='lootlizard.web.catalog.v1';
try {const p=JSON.parse(localStorage.getItem(PREFS)||'null');if(p){language=p.language==='hu'?'hu':'en';interval=[1500,3000,5000].includes(p.interval)?p.interval:3000;}}catch{}
const t=key=>translate(key,language);
const put=(id,value)=>{$(id).textContent=String(value);};
const errorText=error=>String(error?.message||error).slice(0,700);
function performanceSnapshot(){return{requestedFrameRate:captureFps,settings:stream?readCaptureSettings(stream.getVideoTracks()[0]):lastCaptureSettings,mode:diagnosticMode,active:!!stream,events:performanceEvents.slice()};}
function recordPerformance(event){
  performanceEvents.push(event);if(performanceEvents.length>128)performanceEvents.shift();
  if(diagnosticsEnabled)$('performance-readout').textContent=JSON.stringify({requestedFrameRate:captureFps,settings:stream?readCaptureSettings(stream.getVideoTracks()[0]):lastCaptureSettings,constraints:lastConstraintResult,mode:diagnosticMode,lastEvent:event},null,2);
}

function request(type,payload={},transfer=[]) {
  const run=()=>new Promise((resolve,reject)=>{
    if(workerFailed){reject(Error('Reload this page to restart the recognition engine.'));return;}
    const id=++nextId;
    const timeout=setTimeout(()=>{
      pending.delete(id);workerFailed=true;worker.terminate();
      for(const p of pending.values()){clearTimeout(p.timeout);p.reject(Error('Recognition engine timed out. Reload this page.'));}
      pending.clear();stop();phase='error';detail='Recognition engine timed out. Reload this page.';render();reject(Error(detail));
    },type==='init'?240000:60000);
    pending.set(id,{resolve,reject,timeout});worker.postMessage({id,type,...payload},transfer);
  });
  const result=queue.then(run);queue=result.catch(()=>{});return result;
}
worker.onmessage=({data})=>{
  if(data.type==='progress'){put('engine-status',data.message);return;}
  const p=pending.get(data.id);if(!p)return;pending.delete(data.id);clearTimeout(p.timeout);
  data.type==='error'?p.reject(Error(data.reason)):p.resolve(data);
};
worker.onerror=event=>{
  workerFailed=true;for(const p of pending.values()){clearTimeout(p.timeout);p.reject(Error(event.message||'Recognition worker failed.'));}pending.clear();
  stop();phase='error';detail='Recognition worker failed. Reload this page.';put('engine-status',detail);render();
};

function savePreferences(){try {if(remember)localStorage.setItem(PREFS,JSON.stringify({language,interval}));else localStorage.removeItem(PREFS);}catch{}}
function displayResult(){return matchMemory.current?.result||null;}
function currentMap(){return maps.concat(demo.map).find(m=>m.id===displayResult()?.registration?.mapId)||null;}
function targets(){const map=currentMap(),result=displayResult();if(!map)return[];const visible=new Map((result.points||[]).map(p=>[p.id,p]));return orderTargets(map,result.position,result.zone).map(p=>({...p,...visible.get(p.id)}));}
function clearGuidance(){session.invalidate();matchMemory.reset();nonMatchGate.reset();contextReader.terminate();footerDescriptor=null;lastContextCheck=0;contextUnavailable=false;waitingForMatch=false;render();}
function resetMatch(){clearGuidance();waitingForMatch=true;status('unknown','Match ended. Waiting for a new map.');schedule();}
function status(next,message=''){phase=next;detail=message;render();}
function ageText(timestamp){return `${Math.max(0,Math.floor((Date.now()-timestamp)/1000))} s ${t('ago')}`;}
function updateAge(){
  const snapshot=matchMemory.current,age=snapshot?Date.now()-snapshot.mapUpdatedAt:null;
  put('snapshot-age',snapshot?ageText(snapshot.mapUpdatedAt):t('No current result'));
  put('position-status',snapshot?.result.position?`${t('Last known position · identity unverified')} · ${ageText(snapshot.positionUpdatedAt)}`:t('Position unknown · distances unavailable'));
  put('circle-status',snapshot?.result.zone?`${t('Last known circle')} · ${ageText(snapshot.zoneUpdatedAt)}`:t('No circle recognized'));
  return age;
}
function renderStage(map){
  const connected=!!stream;
  const snapshot=matchMemory.current;
  const viewport=snapshot?mapViewport(snapshot.result.registration.matrix,snapshot.frame.width,snapshot.frame.height):null;
  const view=crop?'crop':map&&viewport?'map':phase==='error'?'error':connecting?'connecting':connected?(phase==='scanning'?'scanning':'waiting'):'setup';
  $('map-stage').dataset.view=view;
  canvas.hidden=!['map','crop'].includes(view);
  $('canvas-empty').hidden=!canvas.hidden;
  $('setup-steps').hidden=view!=='setup';
  $('stage-hint').hidden=view!=='setup';
  $('connect-source').hidden=connected||connecting||view==='map'||view==='crop';
  $('connect-source').disabled=$('start-sharing').disabled;
  $('retained-banner').hidden=view!=='map'||phase==='recognized';
  $('reset-match').disabled=!snapshot;
  const messages={
    setup:['Start PUBG','Start PUBG, then connect its window.'],
    connecting:['Choose your PUBG window','Select the PUBG window or the monitor showing the game in the browser picker.'],
    waiting:['Open the map for automatic recognition','Keep playing. LootLizard checks for the map automatically.'],
    scanning:['Checking the map…','Keep playing. LootLizard checks for the map automatically.'],
    error:['Map recognition unavailable',detail||'Reload this page to restart the recognition engine.'],
  };
  const [title,message]=view==='waiting'&&waitingForMatch?['Waiting for a new match','Match ended. Waiting for a new map.']:messages[view]||messages.waiting;
  put('stage-title',t(title));put('stage-detail',t(message));
  $('source-panel').hidden=!connected;
  put('source-status',t(!connected?'No source connected':stream.getVideoTracks()[0]?.muted?'Screen capture is paused.':hasSourcePreview?'Source preview · updates only when scanned':'Waiting for a readable source…'));
}
function render(){
  const result=displayResult(),map=currentMap(),points=targets();
  const names={loading:'Loading recognition engine…',idle:'Ready when you are',scanning:'Checking image…',recognized:'Map recognized',unknown:'No verified map',stopped:'Sharing stopped',error:'Could not process image',cropping:'Select the complete map'};
  const retained=!!map&&phase!=='recognized'&&phase!=='cropping';
  put('recognition-status',t(retained?'Map retained':names[phase]||phase));put('recognition-detail',t(retained?(contextUnavailable?'Match context unavailable · map retained':'Open the map in game to refresh position and circle.'):detail||'Open the full map in game. Targets appear automatically when it is recognized.'));
  if(engine&&!workerFailed)put('engine-status',`${t('Local engine ready')} · OpenCV ${engine.opencv}`);
  put('metadata-status',`${t(metadataKey)} · ${revision}`);
  $('recognition-indicator').className=`status-indicator ${map?'is-ready':phase==='error'?'is-error':phase==='scanning'?'is-warning':''}`;
  put('map-name',map?.name||t('Waiting for a map'));put('room-count',points.length);
  put('inside-count',result?.zone?points.filter(p=>p.inside).length:'—');
  put('capture-status',t(session.source==='screen'?'Sharing screen':session.source==='demo'?'Synthetic demo':session.source==='image'?'Local image':'Not sharing'));
  put('last-update',matchMemory.current?new Date(matchMemory.current.mapUpdatedAt).toLocaleTimeString(language==='hu'?'hu-HU':'en-GB'):'—');
  updateAge();
  put('scan-duration',result?.timings?`${Math.round(result.timings.totalMs)} ms`:'—');
  $('start-sharing').disabled=!engine||configuring>0||workerFailed||connecting||!!stream;
  $('stop-sharing').disabled=!session.active&&!stream&&!connecting;
  renderStage(map);$('demo-banner').hidden=!demoMode||canvas.hidden;
  $('empty-targets').hidden=!!points.length;
  const rows=points.map((p,index)=>{
    const row=document.createElement('tr');if(p.inside)row.className='is-inside';
    for(const value of [index+1,p.name,p.inside===null?'—':t(p.inside?'Inside':'Outside'),p.distance===null?'—':Math.round(p.distance).toLocaleString(language==='hu'?'hu-HU':'en-GB')]){const cell=document.createElement('td');cell.textContent=String(value);row.append(cell);}
    return row;
  });$('target-list').replaceChildren(...rows);draw(points);
}
function draw(points=targets(),force=false){
  // Status/age changes do not require uploading the same snapshot again.
  const overlay=displayResult(),mapFrame=crop?frame:matchMemory.current?.frame;
  if(!force&&drawnFrame===mapFrame&&drawnResult===overlay&&drawnSelection===selection&&drawnCrop===crop&&drawnLanguage===language)return;
  drawnFrame=mapFrame;drawnResult=overlay;drawnSelection=selection;drawnCrop=crop;drawnLanguage=language;
  const viewport=mapFrame&&(crop?{x:0,y:0,width:mapFrame.width,height:mapFrame.height}:overlay?mapViewport(overlay.registration.matrix,mapFrame.width,mapFrame.height):null);
  if(!viewport){setSamplerSize(canvas,1,1);ctx.clearRect(0,0,1,1);return;}
  setSamplerSize(canvas,viewport.width,viewport.height);
  // Only the map pixels enter the main canvas. Gameplay remains a small source
  // thumbnail, rather than a full-size low-frame-rate mirror of the game.
  ctx.putImageData(mapFrame,-viewport.x,-viewport.y,viewport.x,viewport.y,viewport.width,viewport.height);const r=overlay;
  const box=canvas.getBoundingClientRect(),unit=1/Math.max(.05,Math.min(box.width/canvas.width,box.height/canvas.height));
  ctx.save();ctx.translate(-viewport.x,-viewport.y);
  if(r?.registration){
    const matrix=r.registration.matrix;
    if(r.zone){ctx.save();ctx.strokeStyle='#fafafa';ctx.lineWidth=1.5*unit;ctx.setLineDash([7*unit,5*unit]);ctx.beginPath();for(let i=0;i<=100;i++){const a=i*Math.PI/50,p=project(matrix,r.zone.centerX+Math.cos(a)*r.zone.radius,r.zone.centerY+Math.sin(a)*r.zone.radius);if(p)i?ctx.lineTo(...p):ctx.moveTo(...p);}ctx.stroke();ctx.restore();}
    points.forEach((point,index)=>{
      if(!point.visible)return;const p=project(matrix,point.x,point.y);if(!p)return;const[x,y]=p;
      ctx.save();ctx.translate(x,y);ctx.scale(unit,unit);ctx.strokeStyle='#0b1118';ctx.lineWidth=2;ctx.fillStyle=point.inside?'#55e0d0':'#f6bd69';ctx.beginPath();ctx.arc(0,0,3.5,0,Math.PI*2);ctx.fill();ctx.stroke();
      ctx.strokeStyle=ctx.fillStyle;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(4,-4);ctx.lineTo(10,-13);ctx.stroke();ctx.fillStyle='#101923';ctx.fillRect(8,-28,23,19);ctx.strokeRect(8,-28,23,19);ctx.fillStyle=point.inside?'#55e0d0':'#f6bd69';ctx.font='bold 12px sans-serif';ctx.textAlign='center';ctx.fillText(String(index+1),19.5,-14);ctx.restore();
    });
    if(r.position){const p=project(matrix,r.position.x,r.position.y);if(p){ctx.save();ctx.translate(...p);ctx.scale(unit,unit);ctx.strokeStyle='#7ae8ff';ctx.lineWidth=2;ctx.beginPath();ctx.arc(0,0,7,0,Math.PI*2);ctx.moveTo(-12,0);ctx.lineTo(12,0);ctx.moveTo(0,-12);ctx.lineTo(0,12);ctx.stroke();ctx.font='bold 12px sans-serif';ctx.fillStyle='#7ae8ff';ctx.fillText(t('YOU?'),13,18);ctx.restore();}}
  }
  if(selection){const{x,y,side}=selection;ctx.fillStyle='#45dac627';ctx.fillRect(x,y,side,side);ctx.strokeStyle='#55e0d0';ctx.lineWidth=2;ctx.strokeRect(x,y,side,side);}
  ctx.restore();
}

function stop(){
  sourceGeneration++;clearTimeout(timer);timer=null;session.stop();
  matchMemory.reset();nonMatchGate.reset();contextReader.terminate();footerDescriptor=null;lastContextCheck=0;contextUnavailable=false;waitingForMatch=false;
  if(stream)lastCaptureSettings=readCaptureSettings(stream.getVideoTracks()[0]);
  const old=stream;stream=null;if(old)old.getTracks().forEach(track=>track.stop());video.srcObject=null;
  cancelCrop();demoMode=false;connecting=false;hasSourcePreview=false;frame=null;
  previewContext.clearRect(0,0,sourcePreview.width,sourcePreview.height);
  dimensions='';phase='stopped';detail='';render();
}
function schedule(){clearTimeout(timer);if(session.active&&session.source==='screen')timer=setTimeout(scanScreen,interval);}
function capture(){
  if(!video.videoWidth||!video.videoHeight||video.readyState<2)return null;
  const native=`${video.videoWidth}x${video.videoHeight}`;
  if(dimensions&&native!==dimensions){session.invalidate();footerDescriptor=null;nonMatchGate.reset();contextReader.terminate();lastContextCheck=0;}dimensions=native;
  const size=boundedFrameSize(video.videoWidth,video.videoHeight);
  setSamplerSize(sampler,size.width,size.height);
  sample.drawImage(video,0,0,sampler.width,sampler.height);
  const previewSize=sourcePreviewSize(sampler.width,sampler.height);
  setSamplerSize(sourcePreview,previewSize.width,previewSize.height);
  previewContext.drawImage(sampler,0,0,sourcePreview.width,sourcePreview.height);hasSourcePreview=true;
  return sample.getImageData(0,0,sampler.width,sampler.height);
}
async function analyze(image,{owned=false,captureMetrics={}}={}){
  const ticket=session.issue();if(!ticket)return null;
  const started=performance.now(),metrics={type:'scan',epochMs:performance.timeOrigin+started,...captureMetrics,width:image.width,height:image.height};
  session.result=null;
  frame=owned?image:new ImageData(new Uint8ClampedArray(image.data),image.width,image.height);
  metrics.retainMs=performance.now()-started;
  let stage=performance.now();status('scanning');metrics.initialRenderMs=performance.now()-stage;
  // No reference means no registration is possible. Keep the current preview,
  // but avoid transferring millions of pixels into Python just to abstain.
  if(session.source==='screen'&&!demoMode&&!references.size){
    const result={width:image.width,height:image.height,registration:null,position:null,zone:null,points:[],reason:'No canonical map references are loaded'};
    if(!session.accept(ticket,result))return null;
    stage=performance.now();status('unknown',result.reason);
    Object.assign(metrics,{path:'no-references',resultRenderMs:performance.now()-stage,totalMs:performance.now()-started});recordPerformance(metrics);return result;
  }
  // Transfer a copy: the displayed frame is retained only on this device.
  stage=performance.now();const buffer=new Uint8Array(image.data).buffer;metrics.transferCopyMs=performance.now()-stage;
  try{
    stage=performance.now();
    const result=await request('analyze',{rgba:buffer,width:image.width,height:image.height,context:$('replay-mode').checked?'replay':'live',ticket},[buffer]);
    metrics.workerRoundTripMs=performance.now()-stage;
    if(!session.accept(ticket,result))return null;
    if(result.registration){
      matchMemory.update(result,frame,metrics.captureEpochMs||metrics.epochMs);waitingForMatch=false;contextUnavailable=false;
      nonMatchGate.observe({registeredMap:true});
      if(session.source==='screen'&&!demoMode)footerDescriptor=createFooterDescriptor(frame,{verifiedMap:true});
    }
    stage=performance.now();status(result.registration?'recognized':'unknown',result.registration?'Small anchors mark exact coordinates. Distances are straight-line estimates.':result.reason);
    // Context OCR is lazy, throttled and serial with CV. A missing map/footer
    // alone never ends a match. Stop/reset rejects replies from the old epoch.
    if(!result.registration)await checkMatchContext(frame,ticket);
    Object.assign(metrics,{path:'worker',python:result.timings,resultRenderMs:performance.now()-stage,totalMs:performance.now()-started});recordPerformance(metrics);return result;
  }catch(error){if(session.accepts(ticket)){session.accept(ticket,null);status('error',errorText(error));}throw error;}
}
async function checkMatchContext(image,ticket){
  if(session.source!=='screen'||demoMode||!matchMemory.current)return;
  if(matchFooterDescriptor(image,footerDescriptor).present){
    nonMatchGate.observe({footerPresent:true});contextUnavailable=false;return;
  }
  const now=performance.now(),delay=nonMatchGate.count?6000:12000;
  if(lastContextCheck&&now-lastContextCheck<delay)return;
  lastContextCheck=now;const generation=sourceGeneration,started=performance.now();
  if(!contextReader.getState().ready){
    // Download/initialize lazily without holding the automatic map scan loop.
    // Recognition itself still runs after CV, never beside a CV request.
    const epoch=session.epoch;
    contextReader.prepare().then(ready=>{
      if(generation!==sourceGeneration||epoch!==session.epoch||!matchMemory.current)return;
      recordPerformance({type:'match-context-startup',epochMs:Date.now(),durationMs:performance.now()-started,status:ready?'ready':'unavailable'});
      contextUnavailable=!ready;render();
    });return;
  }
  const observation=await contextReader.read(image);
  if(generation!==sourceGeneration||!session.active||session.epoch!==ticket.epoch||session.sequence!==ticket.sequence||!matchMemory.current)return;
  const evidence=nonMatchGate.observe(observation);
  contextUnavailable=observation.status!=='ok';
  recordPerformance({type:'match-context',epochMs:Date.now(),durationMs:performance.now()-started,status:observation.status,context:evidence.context});
  if(evidence.shouldClear)resetMatch();else render();
}
async function scanScreen(){
  if(!session.active||session.source!=='screen')return;
  if(scanning||configuring||crop){schedule();return;}
  const track=stream?.getVideoTracks()[0];
  if(!track||track.readyState!=='live'){stop();return;}
  if(track.muted){session.invalidate();status('unknown','Screen capture is paused.');schedule();return;}
  if(diagnosticsEnabled&&diagnosticMode==='capture-only'){schedule();return;}
  scanning=true;try{
    const start=performance.now(),image=capture(),captureMs=performance.now()-start;
    if(image){
      if(diagnosticsEnabled&&diagnosticMode==='preview-only'){
        clearGuidance();frame=image;const renderStart=performance.now();status('idle','Performance test: preview only; recognition is paused.');
        recordPerformance({type:'scan',path:'preview-only',epochMs:performance.timeOrigin+start,captureMs,renderMs:performance.now()-renderStart,width:image.width,height:image.height});
      }else await analyze(image,{owned:true,captureMetrics:{captureEpochMs:performance.timeOrigin+start,captureMs}});
    }else{session.invalidate();status('unknown','Waiting for a readable shared image…');}
  }catch{}finally{scanning=false;schedule();}
}
async function setWorkerReferences(useDemo=demoMode){
  const records=useDemo?[{mapId:'demo',image:demo.reference}]:[...references].map(([mapId,r])=>({mapId,image:r.image}));
  const transfer=[];const payload=records.map(({mapId,image})=>{const rgba=new Uint8Array(image.data).buffer;transfer.push(rgba);return{mapId,rgba,width:image.width,height:image.height};});
  return request('references',{references:payload},transfer);
}
async function attachStream(media,token,useDemo=false){
  if(token!==sourceGeneration){media.getTracks().forEach(t=>t.stop());return;}
  stream=media;video.srcObject=media;const track=media.getVideoTracks()[0];if(!track){stop();throw Error('No video track was selected.');}
  lastConstraintResult=null;lastCaptureSettings=readCaptureSettings(track);recordPerformance({type:'capture-start',epochMs:Date.now(),requestedFrameRate:captureFps,settings:lastCaptureSettings});
  track.addEventListener('ended',()=>{if(stream===media)stop();});
  track.addEventListener('mute',()=>{if(stream===media){session.invalidate();nonMatchGate.reset();contextReader.terminate();status('unknown','Screen capture is paused.');}});
  track.addEventListener('unmute',()=>{if(stream===media){lastContextCheck=0;schedule();}});
  try{
    await video.play();await setWorkerReferences(useDemo);
    if(token!==sourceGeneration||track.readyState!=='live')return;
    connecting=false;session.begin('screen');demoMode=useDemo;
    status(diagnosticMode==='capture-only'?'idle':'unknown',diagnosticMode==='capture-only'?'Performance test: capture only; preview and recognition are paused.':'Open the full map in game. Targets appear automatically when it is recognized.');scanScreen();
  }catch(error){if(stream===media)stop();throw error;}
}
function startSharing(){
  // The picker must run directly inside the click's transient user activation.
  stop();const token=sourceGeneration;
  if(!navigator.mediaDevices?.getDisplayMedia){status('error','Screen sharing needs a supported desktop browser on HTTPS or localhost.');return;}
  connecting=true;
  let picked;
  try{picked=navigator.mediaDevices.getDisplayMedia(displayMediaOptions(captureFps));}
  catch(error){connecting=false;status('error',errorText(error));return;}
  status('idle','Select the PUBG window or the monitor showing the game in the browser picker.');
  picked.then(media=>attachStream(media,token)).catch(error=>{if(token===sourceGeneration){connecting=false;status('error',errorText(error));}});
}
async function analyzeImageData(image,{source='image'}={}){
  stop();const token=sourceGeneration;await ready;if(token!==sourceGeneration)return null;demoMode=source==='demo';
  configuring++;try{await setWorkerReferences(demoMode);}finally{configuring--;}
  if(token!==sourceGeneration)return null;session.begin(source);return analyze(image);
}
async function loadDemo(){return analyzeImageData(demo.mapFrame,{source:'demo'});}

async function decodeImage(blob,maxSide=1800){
  if(!['image/png','image/jpeg'].includes(blob.type)||blob.size>64000000)throw Error('Choose a PNG or JPEG smaller than 64 MB.');
  const image=await createImageBitmap(blob);
  try{
    if(image.width*image.height>40000000||Math.max(image.width,image.height)>8192)throw Error('Image dimensions are too large.');
    const scale=Math.min(1,maxSide/Math.max(image.width,image.height),Math.sqrt(4000000/(image.width*image.height)));
    const c=document.createElement('canvas');c.width=Math.round(image.width*scale);c.height=Math.round(image.height*scale);
    const cctx=c.getContext('2d',{willReadFrequently:true});cctx.fillStyle='#000';cctx.fillRect(0,0,c.width,c.height);cctx.drawImage(image,0,0,c.width,c.height);
    return cctx.getImageData(0,0,c.width,c.height);
  }finally{image.close();}
}
async function imageBlob(image){const c=document.createElement('canvas');c.width=image.width;c.height=image.height;c.getContext('2d').putImageData(image,0,0);return new Promise((resolve,reject)=>c.toBlob(blob=>blob?resolve(blob):reject(Error('Could not store reference.')),'image/png'));}
async function addReference(mapId,image){
  if(!maps.some(m=>m.id===mapId))throw Error('Choose an available map first.');
  if(Math.abs(image.width/image.height-1)>.015||Math.min(image.width,image.height)<128)throw Error('Use the complete square map, at least 128 pixels wide.');
  if(!references.has(mapId)&&references.size>=8)throw Error('At most eight map references can be loaded.');
  const old=references.get(mapId);configuring++;clearGuidance();references.set(mapId,{image});
  try{await setWorkerReferences();}catch(error){old?references.set(mapId,old):references.delete(mapId);throw error;}finally{configuring--;renderReferences();render();}
  if(remember){try{await referenceStore('put',{mapId,blob:await imageBlob(image)});}catch{put('reference-status',t('Loaded for this session; browser storage is unavailable.'));}}
  if(session.source==='image'&&frame)await analyze(frame);else schedule();
}
function renderReferences(){
  const list=[...references].map(([id,r])=>{const li=document.createElement('li');li.textContent=`${maps.find(m=>m.id===id)?.name||id} · ${t(r.source==='official'?'Default image':'Custom image')} · ${r.image.width} × ${r.image.height}`;return li;});
  $('reference-list').replaceChildren(...list);$('clear-references').disabled=!engine||configuring>0;
  put('reference-status',referenceWarning?t(referenceWarning):references.size?`${references.size} ${t('map references loaded')}`:t('No references loaded'));
  const selected=$('reference-map').value;$('reference-map').replaceChildren(...maps.map(map=>{const o=document.createElement('option');o.value=map.id;o.textContent=map.name;return o;}));if(maps.some(m=>m.id===selected))$('reference-map').value=selected;
}
async function loadDefaults(){
  const result=await loadAutomaticReferences({knownMapIds:maps.map(map=>map.id),existingMapIds:[...references.keys()],decode:blob=>decodeImage(blob)});
  for(const record of result.loaded)references.set(record.mapId,{image:record.image,source:'official'});
  referenceWarning=result.failures.length?'Some default map images could not be loaded. Use default images to retry.':'';
  return result;
}
function cancelCrop(){crop=null;selection=null;canvas.classList.remove('is-cropping');for(const id of ['save-crop','cancel-crop','crop-help'])if($(id))$(id).hidden=true;}
function startCrop(){if(!frame){status('idle','Start sharing or open an image before selecting a reference.');return;}clearGuidance();crop={image:frame,mapId:$('reference-map').value};selection=null;canvas.classList.add('is-cropping');for(const id of ['save-crop','cancel-crop','crop-help'])$(id).hidden=false;status('cropping','Drag a square around the complete, fully zoomed-out map, then save.');}
function canvasPoint(event){const box=canvas.getBoundingClientRect(),scale=Math.min(box.width/canvas.width,box.height/canvas.height);const left=box.left+(box.width-canvas.width*scale)/2,top=box.top+(box.height-canvas.height*scale)/2;return{x:Math.max(0,Math.min(canvas.width,(event.clientX-left)/scale)),y:Math.max(0,Math.min(canvas.height,(event.clientY-top)/scale))};}
canvas.addEventListener('pointerdown',event=>{if(!crop)return;crop.start=canvasPoint(event);canvas.setPointerCapture(event.pointerId);});
canvas.addEventListener('pointermove',event=>{if(!crop?.start||!canvas.hasPointerCapture(event.pointerId))return;const p=canvasPoint(event),s=crop.start;const side=Math.min(Math.abs(p.x-s.x),Math.abs(p.y-s.y));selection={x:Math.round(p.x<s.x?s.x-side:s.x),y:Math.round(p.y<s.y?s.y-side:s.y),side:Math.round(side)};draw();});
async function saveCrop(){if(!selection||selection.side<128){status('cropping','Select a square at least 128 pixels wide.');return;}const{mapId,image}=crop,{x,y,side}=selection;const c=document.createElement('canvas');c.width=image.width;c.height=image.height;c.getContext('2d').putImageData(image,0,0);const out=document.createElement('canvas');out.width=out.height=Math.min(side,1800);out.getContext('2d').drawImage(c,x,y,side,side,0,0,out.width,out.height);const ref=out.getContext('2d').getImageData(0,0,out.width,out.height);cancelCrop();await addReference(mapId,ref);status('idle','Reference ready. Open the map in game to recognize it.');}

async function updateMetadata(){
  let snapshot;
  try{snapshot=validateSnapshot(await readBoundedJSON(await fetch(FEED_URL,{credentials:'omit',cache:'no-store',signal:AbortSignal.timeout(8000)})));}
  catch{metadataKey='Using saved coordinates';render();return;}
  if(JSON.stringify(snapshot.maps)===JSON.stringify(maps)){revision=snapshot.revision;metadataKey='GitHub coordinates';render();return;}
  // Coordinate refreshes are not match boundaries. Keep the verified pixels,
  // position/circle and their ages while replacing the worker's catalog.
  configuring++;session.invalidate();nonMatchGate.reset();contextReader.terminate();const previous=maps;maps=snapshot.maps;
  try{
    await request('init',{maps:[...maps,demo.map]});for(const id of references.keys())if(!maps.some(m=>m.id===id))references.delete(id);
    await loadDefaults();await setWorkerReferences();revision=snapshot.revision;
    if(matchMemory.current){const map=currentMap();if(map)matchMemory.refreshPoints(map);else clearGuidance();}
    if(remember)try{localStorage.setItem(CATALOG,JSON.stringify(snapshot));}catch{}
    metadataKey='GitHub coordinates';
  }catch(error){maps=previous;status('error',errorText(error));}
  finally{configuring--;renderReferences();render();schedule();}
}

$('start-sharing').addEventListener('click',startSharing);$('connect-source').addEventListener('click',startSharing);$('stop-sharing').addEventListener('click',stop);
$('reset-match').addEventListener('click',resetMatch);
$('load-demo').addEventListener('click',()=>loadDemo().catch(e=>status('error',errorText(e))));
$('open-image').addEventListener('change',async event=>{const file=event.target.files[0];event.target.value='';if(!file)return;stop();const token=sourceGeneration;try{const image=await decodeImage(file,2400);if(token===sourceGeneration)await analyzeImageData(image);}catch(e){if(token===sourceGeneration)status('error',errorText(e));}});
$('reference-file').addEventListener('change',async event=>{const file=event.target.files[0];event.target.value='';if(file)try{await ready;await addReference($('reference-map').value,await decodeImage(file));}catch(e){put('reference-status',errorText(e));}});
$('clear-references').addEventListener('click',async()=>{
  configuring++;clearGuidance();render();
  try{await referenceStore('clear');references.clear();await loadDefaults();await setWorkerReferences();}
  catch(e){referenceWarning=errorText(e);}
  finally{configuring--;renderReferences();render();schedule();}
});
$('crop-reference')?.addEventListener('click',startCrop);$('save-crop')?.addEventListener('click',()=>saveCrop().catch(e=>put('reference-status',errorText(e))));$('cancel-crop')?.addEventListener('click',()=>{cancelCrop();render();schedule();});
$('language-select').value=language;$('scan-interval').value=String(interval);
$('language-select').addEventListener('change',()=>{language=$('language-select').value;applyLanguage(language);savePreferences();renderReferences();render();});
$('scan-interval').addEventListener('change',()=>{interval=Number($('scan-interval').value);savePreferences();schedule();});
$('cache-preferences').addEventListener('change',async()=>{remember=$('cache-preferences').checked;savePreferences();try{if(!remember){localStorage.removeItem(CATALOG);await referenceStore('clear');}else{for(const[mapId,r]of references)if(r.source!=='official')await referenceStore('put',{mapId,blob:await imageBlob(r.image)});}}catch{}});
$('replay-mode').addEventListener('change',()=>{clearGuidance();if(session.active&&session.source!=='screen'&&frame)analyze(frame).catch(()=>{});else schedule();});
window.addEventListener('pagehide',stop);
new ResizeObserver(()=>draw(undefined,true)).observe($('map-stage'));
setInterval(updateAge,1000);

const ready=(async()=>{
  applyLanguage(language);render();
  maps=validateMaps(await Promise.all(['erangel','taego'].map(async id=>readBoundedJSON(await fetch(`../data/${id}.json`)))));
  try{const cached=JSON.parse(localStorage.getItem(CATALOG)||'null');if(cached){validateSnapshot(cached);maps=cached.maps;revision=cached.revision;}}catch{}
  const response=await request('init',{maps:[...maps,demo.map]});engine=response.capabilities;
  put('engine-status',`${t('Local engine ready')} · OpenCV ${engine.opencv}`);
  try{const saved=await referenceStore('read');for(const record of saved.slice(0,8)){if(maps.some(m=>m.id===record.mapId))references.set(record.mapId,{image:await decodeImage(record.blob)});}}catch{references.clear();}
  put('engine-status',t('Preparing default map images…'));await loadDefaults();await setWorkerReferences(false);
  renderReferences();status('idle',references.size?'Share your game screen, then open the full map.':'Default map images are unavailable. Use default images to retry, or import a custom image.');
  updateMetadata().catch(()=>{});setInterval(()=>updateMetadata().catch(()=>{}),60000);return response;
})();
ready.catch(error=>{status('error',errorText(error));put('engine-status',t('Engine unavailable. Reload to retry.'));});
const api={ready,demo:loadDemo,analyzeImageData,stop,getState:()=>({...session.snapshot(),phase,mapId:currentMap()?.id||null,points:targets(),position:displayResult()?.position||null,zone:displayResult()?.zone||null,mapUpdatedAt:matchMemory.current?.mapUpdatedAt||null,positionUpdatedAt:matchMemory.current?.positionUpdatedAt||null,zoneUpdatedAt:matchMemory.current?.zoneUpdatedAt||null,referenceCount:references.size,engine}),getPerformance:performanceSnapshot};
if(['127.0.0.1','localhost'].includes(location.hostname)&&new URLSearchParams(location.search).get('test')==='1')api.startTestStream=async (media,{demo:synthetic=false,withoutReferences=false}={})=>{stop();const token=sourceGeneration;await ready;if(withoutReferences){references.clear();await request('references',{references:[]});renderReferences();}await attachStream(media,token,synthetic);};
window.lootLizard=Object.freeze(api);

if(diagnosticsEnabled){
  $('performance-diagnostics').hidden=false;
  $('capture-rate').addEventListener('change',async()=>{
    const control=$('capture-rate'),requestedFps=Number(control.value),token=sourceGeneration,track=stream?.getVideoTracks()[0];
    captureFps=requestedFps;control.disabled=true;
    try{
      const result=track?await applyCaptureRate(track,requestedFps):null;
      if(token!==sourceGeneration||track!==stream?.getVideoTracks()[0])return;
      lastConstraintResult=result;if(result)lastCaptureSettings=result.settings;
      recordPerformance({type:'capture-rate',epochMs:Date.now(),requestedFrameRate:requestedFps,result});
    }finally{control.disabled=false;}
  });
  $('capture-work').addEventListener('change',()=>{
    diagnosticMode=$('capture-work').value;clearGuidance();
    if(diagnosticMode==='capture-only'){frame=null;status('idle','Performance test: capture only; preview and recognition are paused.');}
    recordPerformance({type:'work-mode',epochMs:Date.now(),mode:diagnosticMode});schedule();
  });
  $('export-performance').addEventListener('click',()=>{
    const url=URL.createObjectURL(new Blob([JSON.stringify(performanceSnapshot(),null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='lootlizard-performance.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  recordPerformance({type:'page-ready',epochMs:Date.now()});
}
