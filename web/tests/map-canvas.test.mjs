import test, {before,after} from 'node:test';
import assert from 'node:assert/strict';
import {MapCanvas} from '../app/map-canvas.mjs';

const previousPath2D=globalThis.Path2D;
class TestPath {constructor(path){this.path=path;}}
before(()=>{globalThis.Path2D=TestPath;});
after(()=>{if(previousPath2D===undefined)delete globalThis.Path2D;else globalThis.Path2D=previousPath2D;});

// Record drawing commands in CSS coordinates and the current device-pixel transform.
class Context {
  constructor() {this.calls=[];this.matrix=[1,0,0,1,0,0];this.stack=[];}
  record(name,args) {this.calls.push({name,args,matrix:[...this.matrix]});}
  setTransform(...matrix) {this.matrix=matrix;this.record('setTransform',matrix);}
  save() {this.stack.push([...this.matrix]);}
  restore() {this.matrix=this.stack.pop();}
  scale(x,y) {this.matrix[0]*=x;this.matrix[1]*=x;this.matrix[2]*=y;this.matrix[3]*=y;this.record('scale',[x,y]);}
  translate(x,y) {this.matrix[4]+=this.matrix[0]*x+this.matrix[2]*y;this.matrix[5]+=this.matrix[1]*x+this.matrix[3]*y;}
}
for(const name of ['clearRect','putImageData','fillRect','drawImage','beginPath','moveTo','lineTo','stroke',
  'strokeRect','fillText','arc','fill']) Context.prototype[name]=function(...args){this.record(name,args);};

class Element {
  constructor() {this.listeners=new Map();this.disabled=false;this.textContent='';}
  addEventListener(name,listener) {
    if(!this.listeners.has(name))this.listeners.set(name,[]);
    this.listeners.get(name).push(listener);
  }
  emit(name,properties={}) {
    const event={button:0,pointerId:1,clientX:310,clientY:245,deltaMode:0,deltaY:0,
      prevented:false,preventDefault(){this.prevented=true;},...properties};
    for(const listener of this.listeners.get(name)??[])listener(event);
    return event;
  }
}

function fixture({width=600,height=450,devicePixelRatio=2}={}) {
  let nextAnimation=1;
  const pending=new Map(), cancelled=[];
  const window={devicePixelRatio,
    requestAnimationFrame(callback){const id=nextAnimation++;pending.set(id,callback);return id;},
    cancelAnimationFrame(id){cancelled.push(id);pending.delete(id);}};
  const canvases=[];
  const document={defaultView:window,createElement(name){assert.equal(name,'canvas');return makeCanvas();}};
  function makeCanvas() {
    const canvas=new Element();canvas.width=300;canvas.height=150;canvas.ctx=new Context();canvas.ownerDocument=document;
    canvas.getContext=kind=>{assert.equal(kind,'2d');return canvas.ctx;};
    canvas.box={left:10,top:20,width,height};canvas.getBoundingClientRect=()=>({...canvas.box});
    canvas.captures=new Set();canvas.setPointerCapture=id=>canvas.captures.add(id);
    canvas.hasPointerCapture=id=>canvas.captures.has(id);
    canvas.releasePointerCapture=id=>{canvas.captures.delete(id);canvas.emit('lostpointercapture',{pointerId:id});};
    canvas.focus=()=>{};canvases.push(canvas);return canvas;
  }
  const canvas=makeCanvas(), classes=new Set(),stage={classList:{add:name=>classes.add(name),remove:name=>classes.delete(name)}};
  const zoomIn=new Element(),zoomOut=new Element(),fit=new Element(),zoomLevel=new Element();
  const viewer=new MapCanvas({canvas,stage,zoomIn,zoomOut,fit,zoomLevel});
  return {viewer,canvas,bitmap:canvases[1],zoomIn,zoomOut,fit,zoomLevel,classes,pending,cancelled,
    flush(){const batch=[...pending.values()];pending.clear();for(const callback of batch)callback();},
    images(){return canvas.ctx.calls.filter(call=>call.name==='drawImage');},
    anchors(){return canvas.ctx.calls.filter(call=>call.name==='arc');},
    uploads(){return canvases[1].ctx.calls.filter(call=>call.name==='putImageData');}};
}

function mapData(mapId='deston',size=1) {
  return {frame:{width:1000*size,height:740*size},
    registration:{mapId,matrix:[[800*size,0,100*size],[0,600*size,70*size],[0,0,1]]},
    viewport:{x:100*size,y:70*size,width:800*size,height:600*size},
    points:[{id:'room',x:.45,y:.55,visible:true,kind:'security_room'}]};
}
const close=(actual,expected)=>assert.ok(Math.abs(actual-expected)<1e-8,`Expected ${actual} ≈ ${expected}`);
const latest=items=>items.at(-1);

test('navigation repaints the cached map without uploading another captured frame', () => {
  const f=fixture(),data=mapData();f.viewer.setMap(data);
  assert.equal(f.uploads().length,1);
  const upload=f.uploads()[0];
  assert.equal(upload.args[0],data.frame);
  assert.deepEqual(upload.args.slice(1),[-100,-70,100,70,800,600]);
  assert.equal(f.bitmap.width,800);assert.equal(f.bitmap.height,600);
  assert.equal(f.canvas.emit('wheel',{deltaY:-200}).prevented,true);f.flush();
  f.canvas.emit('pointerdown');f.canvas.emit('pointermove',{clientX:350,clientY:225});
  f.canvas.emit('pointerup');f.flush();
  f.viewer.setMap({...data,points:[...data.points]});
  assert.equal(f.uploads().length,1,'Wheel, dragging and marker refresh reuse the cropped pixels');
  f.viewer.setMap({...data,frame:{...data.frame}});
  assert.equal(f.uploads().length,2,'A genuinely new capture replaces the cached bitmap once');
});

test('cropped-map pixels and exact location anchors share the zoom and drag transform', () => {
  const f=fixture();f.viewer.setMap(mapData());
  for(const navigate of [()=>{},()=>f.viewer.zoom(2,300,225),()=>{
    f.canvas.emit('pointerdown');f.canvas.emit('pointermove',{clientX:350,clientY:225});f.canvas.emit('pointerup');
  }]) {
    navigate();f.flush();
    const image=latest(f.images()),anchor=latest(f.anchors());
    const [,left,top,width,height]=image.args;
    close(anchor.args[0],left+.45*width);close(anchor.args[1],top+.55*height);
    assert.equal(anchor.args[2],2.2,'Exact-location dots retain their CSS radius at every zoom');
    assert.deepEqual(anchor.matrix,image.matrix,'Pixel density applies equally to the map and its dots');
    const icon=f.canvas.ctx.calls.filter(call=>call.name==='stroke'&&call.args[0] instanceof TestPath).at(-1);
    close(icon.matrix[0],image.matrix[0]*16/24);
    close(icon.matrix[3],image.matrix[3]*16/24);
  }
});

test('fit, minimum and maximum zoom controls reflect the displayed map', () => {
  const f=fixture();
  assert.equal(f.zoomLevel.textContent,'100%');
  assert.ok(f.zoomIn.disabled&&f.zoomOut.disabled&&f.fit.disabled);
  f.viewer.setMap(mapData());
  assert.equal(f.zoomIn.disabled,false);assert.equal(f.zoomOut.disabled,true);assert.equal(f.fit.disabled,true);
  f.zoomIn.emit('click');f.flush();assert.equal(f.zoomLevel.textContent,'140%');
  f.viewer.zoom(1000);f.flush();
  assert.equal(f.zoomLevel.textContent,'800%');assert.equal(f.zoomIn.disabled,true);assert.equal(f.zoomOut.disabled,false);
  f.fit.emit('click');f.flush();
  assert.equal(f.zoomLevel.textContent,'100%');assert.equal(f.fit.disabled,true);
  assert.deepEqual(latest(f.images()).args.slice(1),[0,0,600,450]);
  f.viewer.zoom(.001);f.flush();assert.equal(f.zoomLevel.textContent,'100%');
});

test('fresh captures of the same map preserve normalized focus; another map and clear reset it', () => {
  const f=fixture();f.viewer.setMap(mapData());f.viewer.zoom(3,250,200);f.flush();
  f.canvas.emit('pointerdown');f.canvas.emit('pointermove',{clientX:340,clientY:260});f.canvas.emit('pointerup');f.flush();
  const focused={...f.viewer.view};
  f.viewer.setMap(mapData('deston',2));
  assert.deepEqual(f.viewer.view,focused,'New capture dimensions cannot reset the player’s inspection area');
  f.canvas.emit('pointerdown');assert.equal(f.classes.has('is-dragging'),true);
  f.viewer.setMap(mapData('taego'));
  assert.deepEqual(f.viewer.view,{zoom:1,centerX:.5,centerY:.5});
  assert.equal(f.classes.has('is-dragging'),false);assert.equal(f.canvas.captures.size,0);
  f.viewer.zoom(4);f.flush();f.viewer.clear();
  assert.deepEqual(f.viewer.view,{zoom:1,centerX:.5,centerY:.5});
  assert.equal(f.viewer.data,null);assert.equal(f.canvas.width,1);assert.equal(f.bitmap.width,1);
  f.viewer.setMap(mapData('taego'));assert.equal(f.viewer.view.zoom,1);
});

test('many navigation events coalesce into one animation frame, and clear cancels the pending repaint', () => {
  const f=fixture();f.viewer.setMap(mapData());const before=f.images().length;
  for(let index=0;index<8;index++)f.canvas.emit('wheel',{deltaY:-20});
  assert.equal(f.pending.size,1);assert.equal(f.images().length,before);
  f.flush();assert.equal(f.images().length,before+1);assert.equal(f.uploads().length,1);
  f.viewer.zoom(1.2);const queued=[...f.pending.values()];
  f.canvas.emit('pointerdown');assert.equal(f.canvas.captures.size,1);
  f.viewer.clear();assert.equal(f.pending.size,0);assert.equal(f.cancelled.length,1);
  assert.equal(f.canvas.captures.size,0);assert.equal(f.classes.has('is-dragging'),false);
  const clearedCount=f.images().length;
  // Even a stale callback delivered at the cancellation boundary cannot resurrect the map.
  for(const callback of queued)callback();
  f.canvas.emit('pointermove',{clientX:400,clientY:400});
  assert.equal(f.canvas.emit('wheel',{deltaY:-200}).prevented,false);
  f.flush();assert.equal(f.images().length,clearedCount);assert.equal(f.pending.size,0);
});

test('a cancelled drag releases capture and later movement does not change the view', () => {
  const f=fixture();f.viewer.setMap(mapData());f.viewer.zoom(2);f.flush();
  f.canvas.emit('pointerdown');f.canvas.emit('pointermove',{clientX:340,clientY:270});
  f.canvas.emit('pointercancel');f.flush();const stopped={...f.viewer.view};
  assert.equal(f.classes.has('is-dragging'),false);assert.equal(f.canvas.captures.size,0);
  f.canvas.emit('pointermove',{clientX:500,clientY:400});f.flush();
  assert.deepEqual(f.viewer.view,stopped);assert.equal(f.pending.size,0);
  f.canvas.emit('pointerdown',{button:2});
  assert.equal(f.canvas.captures.size,0,'Secondary button cannot start a map drag');
});

test('viewport changes redraw the cache at bounded pixel density without moving the normalized focus', () => {
  const f=fixture({devicePixelRatio:3});f.viewer.setMap(mapData());f.viewer.zoom(4,300,225);f.flush();
  assert.equal(f.canvas.width,1200);assert.equal(f.canvas.height,900);
  const focused={...f.viewer.view};f.canvas.box.width=4000;f.canvas.box.height=3000;f.viewer.draw();
  assert.equal(f.canvas.width,2560);assert.equal(f.canvas.height,1920);
  assert.deepEqual(f.viewer.view,focused);assert.equal(f.uploads().length,1);
  const image=latest(f.images());close(image.matrix[0],.64);close(image.matrix[3],.64);
  const anchor=latest(f.anchors());close(anchor.args[0],image.args[1]+.45*image.args[3]);
  close(anchor.args[1],image.args[2]+.55*image.args[4]);
});
