import {project} from './session.mjs';
import {setSamplerSize} from './capture.mjs';
import {fitView,viewTransform,panView,zoomViewAt,MIN_ZOOM,MAX_ZOOM} from './map-navigation.mjs';
import {locationKind,layoutLocationMarkers,drawLocationMarkers} from './location-markers.mjs';

/** A retained map viewer. Pointer/keyboard changes repaint cached pixels only. */
export class MapCanvas {
  constructor({canvas,stage,zoomIn,zoomOut,fit,zoomLevel}) {
    Object.assign(this,{canvas,stage,zoomIn,zoomOut,fit,zoomLevel});
    this.window=canvas.ownerDocument.defaultView;
    this.ctx=canvas.getContext('2d');
    this.bitmap=canvas.ownerDocument.createElement('canvas');
    this.bitmapContext=this.bitmap.getContext('2d');
    this.view=fitView();this.data=null;this.drag=null;this.animation=null;
    zoomIn.addEventListener('click',()=>this.zoom(1.4));
    zoomOut.addEventListener('click',()=>this.zoom(1/1.4));
    fit.addEventListener('click',()=>{this.view=fitView();this.schedule();});
    canvas.addEventListener('wheel',event=>{
      if(!this.data)return;
      event.preventDefault();
      const unit=event.deltaMode===1?16:event.deltaMode===2?this.metrics().height:1;
      const delta=Math.max(-240,Math.min(240,event.deltaY*unit));
      const point=this.pointer(event);this.zoom(Math.exp(-delta*.0025),point.x,point.y);
    },{passive:false});
    canvas.addEventListener('dblclick',event=>{
      if(!this.data)return;event.preventDefault();
      const point=this.pointer(event);this.zoom(event.shiftKey ? .5 : 2,point.x,point.y);
    });
    canvas.addEventListener('pointerdown',event=>{
      if(!this.data||event.button!==0||this.drag)return;
      event.preventDefault();canvas.focus({preventScroll:true});
      this.drag={id:event.pointerId,x:event.clientX,y:event.clientY};
      canvas.setPointerCapture(event.pointerId);stage.classList.add('is-dragging');
    });
    canvas.addEventListener('pointermove',event=>{
      if(!this.data||this.drag?.id!==event.pointerId)return;
      this.view=panView(this.view,event.clientX-this.drag.x,event.clientY-this.drag.y,this.metrics());
      this.drag.x=event.clientX;this.drag.y=event.clientY;this.schedule();
    });
    for(const name of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(name,event=>{
      if(this.drag?.id===event.pointerId)this.endDrag();
    });
    canvas.addEventListener('keydown',event=>{
      if(!this.data||event.ctrlKey||event.metaKey||event.altKey)return;
      const step=event.shiftKey?160:64,arrows={ArrowLeft:[step,0],ArrowRight:[-step,0],ArrowUp:[0,step],ArrowDown:[0,-step]};
      if(arrows[event.key])this.view=panView(this.view,...arrows[event.key],this.metrics());
      else if(event.key==='+'||event.key==='=')this.zoom(1.4);
      else if(event.key==='-'||event.key==='_')this.zoom(1/1.4);
      else if(event.key==='0'||event.key==='Home')this.view=fitView();
      else return;
      event.preventDefault();this.schedule();
    });
    this.clear();
  }
  pointer(event) {
    const box=this.canvas.getBoundingClientRect();
    return {x:event.clientX-box.left,y:event.clientY-box.top};
  }
  metrics() {
    const box=this.canvas.getBoundingClientRect();
    return {width:box.width,height:box.height,mapWidth:this.bitmap.width,mapHeight:this.bitmap.height};
  }
  endDrag() {
    const drag=this.drag;this.drag=null;this.stage.classList.remove('is-dragging');
    if(drag&&this.canvas.hasPointerCapture(drag.id))this.canvas.releasePointerCapture(drag.id);
  }
  clear() {
    this.endDrag();
    if(this.animation!==null)this.window.cancelAnimationFrame(this.animation);
    this.animation=null;this.data=null;this.view=fitView();
    setSamplerSize(this.bitmap,1,1);setSamplerSize(this.canvas,1,1);
    this.ctx.clearRect(0,0,1,1);this.updateControls();
  }
  setMap({frame,registration,viewport,points}) {
    const previous=this.data;
    if(previous?.registration.mapId!==registration.mapId){this.endDrag();this.view=fitView();}
    if(previous?.frame!==frame||previous?.registration!==registration){
      setSamplerSize(this.bitmap,viewport.width,viewport.height);
      this.bitmapContext.clearRect(0,0,this.bitmap.width,this.bitmap.height);
      this.bitmapContext.putImageData(frame,-viewport.x,-viewport.y,viewport.x,viewport.y,viewport.width,viewport.height);
    }
    this.data={frame,registration,viewport,points};this.draw();
  }
  zoom(factor,x,y) {
    if(!this.data)return;
    this.view=zoomViewAt(this.view,factor,x,y,this.metrics());this.schedule();
  }
  schedule() {
    if(this.animation!==null||!this.data)return;
    this.animation=this.window.requestAnimationFrame(()=>{this.animation=null;this.draw();});
  }
  updateControls() {
    this.zoomLevel.textContent=`${Math.round(this.view.zoom*100)}%`;
    this.zoomOut.disabled=!this.data||this.view.zoom<=MIN_ZOOM+1e-8;
    this.zoomIn.disabled=!this.data||this.view.zoom>=MAX_ZOOM-1e-8;
    this.fit.disabled=!this.data||this.view.zoom<=MIN_ZOOM+1e-8;
  }
  draw() {
    if(!this.data)return;
    const metrics=this.metrics(),transform=viewTransform(this.view,metrics);if(!transform)return;
    this.view={zoom:transform.zoom,centerX:transform.centerX,centerY:transform.centerY};
    // Bound the backing bitmap even on very large/high-density displays.
    const ratio=Math.min(2,Math.max(1,this.window.devicePixelRatio||1),2560/metrics.width,2560/metrics.height);
    setSamplerSize(this.canvas,Math.max(1,Math.round(metrics.width*ratio)),Math.max(1,Math.round(metrics.height*ratio)));
    const ctx=this.ctx;ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,this.canvas.width,this.canvas.height);
    ctx.save();ctx.scale(this.canvas.width/metrics.width,this.canvas.height/metrics.height);
    ctx.fillStyle='#080e14';ctx.fillRect(0,0,metrics.width,metrics.height);
    ctx.drawImage(this.bitmap,transform.offsetX,transform.offsetY,transform.drawWidth,transform.drawHeight);
    const {registration,viewport,points}=this.data;
    const projected=points.flatMap((point,index)=>{
      if(!point.visible)return[];const location=project(registration.matrix,point.x,point.y);if(!location)return[];
      return [{id:point.id,index:index+1,kind:locationKind(point),
        x:transform.offsetX+(location[0]-viewport.x)*transform.scale,
        y:transform.offsetY+(location[1]-viewport.y)*transform.scale}];
    });
    drawLocationMarkers(ctx,layoutLocationMarkers(projected,metrics.width,metrics.height));ctx.restore();this.updateControls();
  }
}
