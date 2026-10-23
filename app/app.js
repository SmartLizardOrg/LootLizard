import {CaptureSession} from './session.mjs';
import {validateCatalog,readBoundedJSON} from './metadata.mjs';
import {createDemo} from './demo.mjs';
import {applyLanguage,translate} from './i18n.mjs';
import {displayMediaOptions,readCaptureSettings,applyCaptureRate,boundedFrameSize,setSamplerSize} from './capture.mjs';
import {AUTOMATIC_REFERENCES,fetchReference,loadAutomaticReferences} from './automatic-references.mjs';
import {browserPreferenceStorage,loadPreferences,savePreferences,SCAN_INTERVALS,nextScanDelay,captureRateForInterval} from './preferences.mjs';
import {mapViewport,sourcePreviewSize} from './map-view.mjs';
import {MatchMapMemory} from './match-memory.mjs';
import {NonMatchGate,createFooterDescriptor,matchFooterDescriptor} from './match-context.mjs';
import {createMatchContextReader} from './match-context-reader.mjs';
import {locationKind,locationLabel,locationIconSVG,presentLocationKinds} from './location-markers.mjs';
import {MapCanvas} from './map-canvas.mjs';
import {ManualMapSelection} from './manual-map.mjs';

const $=id=>document.getElementById(id);
const testing=['127.0.0.1','localhost'].includes(location.hostname)&&new URLSearchParams(location.search).get('test')==='1';
// Synthetic fixtures and processing controls have no player-facing controls.
const demo=testing?createDemo():null,session=new CaptureSession(),references=new Map();
const matchMemory=new MatchMapMemory(),nonMatchGate=new NonMatchGate(),contextReader=createMatchContextReader();
const canvas=$('map-canvas'),video=$('capture-video');
const mapCanvas=new MapCanvas({canvas,stage:$('map-stage'),zoomIn:$('map-zoom-in'),zoomOut:$('map-zoom-out'),fit:$('map-fit'),zoomLevel:$('map-zoom-level')});
const sourcePreview=$('source-preview'),previewContext=sourcePreview.getContext('2d');
const sampler=document.createElement('canvas'),sample=sampler.getContext('2d',{willReadFrequently:true});
let worker=null,mode='manual',modeGeneration=0,automaticReady=null,automaticAbort=null;
let nextId=0,queue=Promise.resolve(),pending=new Map(),workerFailed=false;
let maps=[],engine=null,prepared=false,frame=null,stream=null,timer=null,scanning=false;
let phase='loading',detail='',sourceGeneration=0,connecting=false,hasSourcePreview=false,sourceRecognized=false;
let footerDescriptor=null,lastContextCheck=0,waitingForMatch=false,dimensions='',demoMode=false;
let drawnFrame=null,drawnResult=null,drawnLanguage='',lastScanAt=null,diagnosticMode='full';
let catalogFailed=false;
const preferenceStorage=browserPreferenceStorage(window);
let {language,interval}=loadPreferences(preferenceStorage);
let captureFps=captureRateForInterval(interval),lastCaptureSettings={},lastConstraintResult=null,rateQueue=Promise.resolve();
const performanceEvents=[],t=key=>translate(key,language),put=(id,value)=>{$(id).textContent=String(value);};
const allMaps=()=>demo?[...maps,demo.map]:maps;
const manualSelection=new ManualMapSelection({load:async(map,signal)=>{
  const reference=AUTOMATIC_REFERENCES.find(record=>record.mapId===map.id);
  return decodeImage(await fetchReference(reference,{signal}));
},onChange:()=>render()});
function recordPerformance(event){performanceEvents.push(event);if(performanceEvents.length>128)performanceEvents.shift();}
function performanceSnapshot(){return{requestedFrameRate:captureFps,settings:stream?readCaptureSettings(stream.getVideoTracks()[0]):lastCaptureSettings,mode:diagnosticMode,active:!!stream,events:performanceEvents.slice()};}
function request(type,payload={},transfer=[]){
  const activeWorker=worker;
  const run=()=>new Promise((resolve,reject)=>{
    if(!activeWorker||worker!==activeWorker||mode!=='auto'||workerFailed){reject(Error('Recognition unavailable'));return;}
    const id=++nextId,timeout=setTimeout(()=>{
      if(worker!==activeWorker)return;
      pending.delete(id);workerFailed=true;activeWorker.terminate();
      for(const item of pending.values()){clearTimeout(item.timeout);item.reject(Error('Recognition unavailable'));}
      pending.clear();stop();status('error','LootLizard stopped responding. Refresh this page to try again.');reject(Error('Recognition unavailable'));
    },type==='init'?240000:60000);
    pending.set(id,{resolve,reject,timeout});activeWorker.postMessage({id,type,...payload},transfer);
  });
  const result=queue.then(run);queue=result.catch(()=>{});return result;
}
function createWorker(){
  const activeWorker=new Worker(new URL('./vision-worker.js',import.meta.url),{type:'module'});worker=activeWorker;
  activeWorker.onmessage=({data})=>{
  if(worker!==activeWorker)return;
  if(data.type==='progress')return;
  const item=pending.get(data.id);if(!item)return;pending.delete(data.id);clearTimeout(item.timeout);
  data.type==='error'?item.reject(Error(data.reason)):item.resolve(data);
  };
  activeWorker.onerror=()=>{
  if(worker!==activeWorker||mode!=='auto')return;
  workerFailed=true;for(const item of pending.values()){clearTimeout(item.timeout);item.reject(Error('Recognition unavailable'));}pending.clear();
  stop();status('error','LootLizard stopped responding. Refresh this page to try again.');
  };
}
function releaseEngine(){
  automaticAbort?.abort();automaticAbort=null;worker?.terminate();worker=null;
  for(const item of pending.values()){clearTimeout(item.timeout);item.reject(Error('Recognition cancelled'));}
  pending.clear();queue=Promise.resolve();automaticReady=null;references.clear();prepared=false;engine=null;workerFailed=false;
}
function displaySnapshot(){return mode==='manual'?manualSelection.current:matchMemory.current;}
function displayResult(){return displaySnapshot()?.result||null;}
function currentMap(){return mode==='manual'?manualSelection.current?.map||null:allMaps().find(map=>map.id===displayResult()?.registration?.mapId)||null;}
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
  const manual=mode==='manual';
  $('auto-controls').hidden=manual;$('auto-status-card').hidden=manual;$('auto-map-footer').hidden=manual;$('scan-settings').hidden=manual;
  $('mode-manual').setAttribute('aria-pressed',String(manual));$('mode-auto').setAttribute('aria-pressed',String(!manual));
  $('reset-map').hidden=!manual||(!manualSelection.current&&!manualSelection.loadingMapId);
  put('privacy-message',t(manual?'Choose a map or connect PUBG for automatic recognition.':'Your screen stays on this device. Stop sharing whenever you want.'));
  $('map-picker').hidden=!manual||!!map;
  if(manual){
    const view=map?'map':'picker';$('map-stage').dataset.view=view;canvas.hidden=!map;
    $('canvas-empty').hidden=true;$('map-navigation').hidden=!map;$('retained-banner').hidden=true;$('source-panel').hidden=true;
    const message=catalogFailed?'Could not prepare LootLizard. Refresh this page to try again.':manualSelection.phase==='error'?'Map could not be opened. Choose another map or try again.':manualSelection.phase==='loading'?'Loading map…':'';
    put('map-picker-message',t(message));$('map-picker-message').hidden=!message;
    for(const tile of $('map-grid').children)tile.setAttribute('aria-busy',String(tile.dataset.mapId===manualSelection.loadingMapId));
    return;
  }
  const connected=!!stream,snapshot=matchMemory.current;
  const viewport=snapshot?mapViewport(snapshot.result.registration.matrix,snapshot.frame.width,snapshot.frame.height):null;
  const view=map&&viewport?'map':phase==='error'?'error':connecting?'connecting':connected?'waiting':'setup';
  $('map-stage').dataset.view=view;canvas.hidden=view!=='map';$('canvas-empty').hidden=!canvas.hidden;
  $('map-navigation').hidden=view!=='map';
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
  put('map-name',map?.name||t(mode==='manual'?'Your maps':'Waiting for a map'));put('room-count',points.length);
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
  const empty=$('empty-targets').querySelector('p');if(empty)empty.textContent=t(map?'No locations listed for this map yet.':mode==='manual'?'Choose a map to see its locations.':'Locations appear here when your map is recognized.');
  const rows=points.map((point,index)=>{
    const row=document.createElement('tr'),rank=document.createElement('td'),cell=document.createElement('td'),icon=document.createElement('span'),name=document.createElement('span');
    rank.textContent=String(index+1);icon.className='location-icon';icon.innerHTML=locationIconSVG(locationKind(point));icon.setAttribute('role','img');icon.setAttribute('aria-label',t(locationLabel(locationKind(point))));
    name.textContent=point.name;cell.className='location-cell';cell.append(icon,name);row.append(rank,cell);return row;
  });$('target-list').replaceChildren(...rows);draw(points);
}
function draw(points=targets(),force=false){
  const overlay=displayResult(),mapFrame=displaySnapshot()?.frame;
  if(!force&&drawnFrame===mapFrame&&drawnResult===overlay&&drawnLanguage===language)return;
  drawnFrame=mapFrame;drawnResult=overlay;drawnLanguage=language;
  const viewport=mapFrame&&overlay?mapViewport(overlay.registration.matrix,mapFrame.width,mapFrame.height):null;
  if(!viewport){mapCanvas.clear();return;}
  mapCanvas.setMap({frame:mapFrame,registration:overlay.registration,viewport,points});
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
function schedule(){clearTimeout(timer);timer=null;if(mode==='auto'&&session.active&&session.source==='screen'&&!scanning)timer=setTimeout(scanScreen,nextScanDelay(interval,lastScanAt,performance.now()));}
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
  }catch(error){if(session.accepts(ticket)){session.accept(ticket,null);status('error','Could not read the map. Keep it open and try again.');throw error;}return null;}
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
  if(mode!=='auto'||!session.active||session.source!=='screen'||scanning)return;
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
  if(mode!=='auto'||token!==sourceGeneration){media.getTracks().forEach(track=>track.stop());return;}
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
  if(mode!=='auto'||!prepared||workerFailed)return;
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
function renderMapPicker(){
  $('map-grid').replaceChildren(...maps.flatMap(map=>{
    const reference=AUTOMATIC_REFERENCES.find(record=>record.mapId===map.id);if(!reference)return[];
    const tile=document.createElement('button'),image=document.createElement('img'),name=document.createElement('span'),count=document.createElement('span');
    tile.type='button';tile.className='map-tile';tile.dataset.mapId=map.id;
    image.className='map-tile-image';image.src=reference.url;image.alt='';image.loading='lazy';image.decoding='async';image.width=reference.width;image.height=reference.height;
    name.className='map-tile-name';name.textContent=map.name;count.className='map-tile-count';count.textContent=`${map.points.length} ${t('locations')}`;
    tile.append(image,name,count);tile.addEventListener('click',()=>{if(mode==='manual')manualSelection.select(map);});return[tile];
  }));
}
function selectMode(next){
  if(next!=='manual'&&next!=='auto')return Promise.resolve(null);
  if(mode===next)return next==='auto'?ensureAutomaticEngine():Promise.resolve(null);
  modeGeneration++;stop();releaseEngine();mode=next;manualSelection.reset();phase=next==='auto'?'loading':'idle';detail='';render();
  return next==='auto'?ensureAutomaticEngine():Promise.resolve(null);
}
function ensureAutomaticEngine(){
  if(mode!=='auto')return Promise.resolve(null);
  if(automaticReady)return automaticReady;
  const generation=modeGeneration,abort=new AbortController();automaticAbort=abort;
  const active=()=>mode==='auto'&&generation===modeGeneration&&!abort.signal.aborted;
  automaticReady=(async()=>{
    await catalogReady;if(!active())return null;
    createWorker();const response=await request('init',{maps:allMaps()});if(!active())return null;
    engine=response.capabilities;
    const result=await loadAutomaticReferences({knownMapIds:maps.map(map=>map.id),existingMapIds:[],decode:decodeImage,signal:abort.signal});
    if(!active())return null;
    for(const record of result.loaded)references.set(record.mapId,{image:record.image});
    if(result.failures.length||references.size!==maps.length)throw Error('Incomplete bundled maps');
    await setWorkerReferences(false);if(!active())return null;
    prepared=true;status('idle','Connect PUBG, then open the full map in game.');return response;
  })().catch(error=>{if(active()){status('error','Could not prepare LootLizard. Refresh this page to try again.');throw error;}return null;});
  automaticReady.catch(()=>{});return automaticReady;
}
$('start-sharing').addEventListener('click',startSharing);$('connect-source').addEventListener('click',startSharing);$('stop-sharing').addEventListener('click',stop);$('reset-match').addEventListener('click',resetMatch);
$('mode-manual').addEventListener('click',()=>selectMode('manual'));$('mode-auto').addEventListener('click',()=>selectMode('auto'));$('choose-auto').addEventListener('click',()=>selectMode('auto'));
$('reset-map').addEventListener('click',()=>{if(mode==='manual'){manualSelection.reset();$('map-grid').querySelector('button')?.focus();}});
$('source-details').addEventListener('toggle',()=>{if($('source-details').open&&stream)updatePreview(frame);});
$('language-select').value=language;$('scan-interval').value=String(interval);
$('language-select').addEventListener('change',()=>{language=$('language-select').value==='hu'?'hu':'en';applyLanguage(language);savePreferences(preferenceStorage,{language,interval});renderMapPicker();render();});
$('scan-interval').addEventListener('change',()=>changeInterval(Number($('scan-interval').value)));
window.addEventListener('pagehide',()=>{modeGeneration++;stop();releaseEngine();manualSelection.reset();});new ResizeObserver(()=>draw(undefined,true)).observe($('map-stage'));setInterval(()=>{if(mode==='auto')updateAge();},1000);
window.addEventListener('pageshow',event=>{if(event.persisted&&mode==='auto'){status('loading');ensureAutomaticEngine();}});

const catalogReady=(async()=>{
  applyLanguage(language);render();
  const catalog=validateCatalog(await readBoundedJSON(await fetch('../data/maps.json')));maps=catalog.maps;
  renderMapPicker();render();return catalog;
})();
catalogReady.catch(()=>{catalogFailed=true;status('error','Could not prepare LootLizard. Refresh this page to try again.');});

if(testing){
  async function analyzeImageData(image,{source='image'}={}){
    if(mode!=='auto')selectMode('auto');stop();const token=sourceGeneration;await ensureAutomaticEngine();if(token!==sourceGeneration||mode!=='auto')return null;demoMode=source==='demo';
    await setWorkerReferences(demoMode);if(token!==sourceGeneration)return null;session.begin(source);return analyze(image);
  }
  window.lootLizard=Object.freeze({get ready(){return mode==='auto'?ensureAutomaticEngine():catalogReady;},demo:()=>analyzeImageData(demo.mapFrame,{source:'demo'}),analyzeImageData,stop,
    getState:()=>({...session.snapshot(),mode,manualMapId:manualSelection.current?.map.id||null,workerActive:!!worker,phase:mode==='manual'?manualSelection.phase:phase,mapId:currentMap()?.id||null,points:targets(),position:null,zone:null,mapUpdatedAt:mode==='auto'?matchMemory.current?.mapUpdatedAt||null:null,positionUpdatedAt:null,zoneUpdatedAt:null,referenceCount:references.size,interval,engine}),
    getPerformance:performanceSnapshot,
    configureTestProcessing:mode=>{if(!['full','capture-only','preview-only'].includes(mode))throw Error('Invalid mode');diagnosticMode=mode;clearGuidance();status('idle');schedule();},
    startTestStream:async(media,{demo:synthetic=false,withoutReferences=false}={})=>{if(mode!=='auto')selectMode('auto');stop();const token=sourceGeneration;await ensureAutomaticEngine();if(token!==sourceGeneration||mode!=='auto'){media.getTracks().forEach(track=>track.stop());return;}if(withoutReferences){references.clear();await request('references',{references:[]});}await attachStream(media,token,synthetic);},
  });
}
