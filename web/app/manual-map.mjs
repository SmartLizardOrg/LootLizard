/** A manual selection owns one map image; obsolete loads can never restore it. */
export class ManualMapSelection {
  constructor({load,onChange=()=>{}}) {
    this.load=load;this.onChange=onChange;this.generation=0;this.controller=null;
    this.current=null;this.loadingMapId=null;this.phase='idle';
  }
  reset() {
    this.generation++;this.controller?.abort();this.controller=null;
    this.current=null;this.loadingMapId=null;this.phase='idle';this.onChange();
  }
  async select(map) {
    this.reset();const generation=this.generation,controller=new AbortController();
    this.controller=controller;this.loadingMapId=map.id;this.phase='loading';this.onChange();
    try {
      const frame=await this.load(map,controller.signal);
      if(generation!==this.generation||controller.signal.aborted)return null;
      if(!Number.isInteger(frame?.width)||!Number.isInteger(frame?.height)||frame.width<=0||frame.height<=0||
          frame.width*frame.height>4_000_000||frame.data?.length!==frame.width*frame.height*4)throw Error('Invalid map image');
      const result={registration:{mapId:map.id,matrix:[[frame.width,0,0],[0,frame.height,0],[0,0,1]]},
        points:map.points.map(point=>({...point,visible:true}))};
      this.current={map,frame,result};this.loadingMapId=null;this.controller=null;this.phase='recognized';this.onChange();
      return this.current;
    } catch {
      if(generation!==this.generation||controller.signal.aborted)return null;
      this.controller=null;this.loadingMapId=null;this.phase='error';this.onChange();return null;
    }
  }
}
