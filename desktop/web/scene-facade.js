// Presentation-only factory details. All heights below are absolute above the ground;
// the roof and photovoltaic geometry are never modified by this module.
export const FACADE_DEFAULTS = Object.freeze({enabled:true,wall_material:'metal',wall_color:'#d6dde2',
  trim_color:'#49606c',base_color:'#64717a',door_color:'#3c5969',bay_width_m:6,base_height_m:.6,
  columns:true,window_rows:1,window_width_m:2.4,window_height_m:1.2,window_sill_m:3.8,
  front_edge:null,doors:2,door_width_m:4,door_height_m:4,canopy_depth_m:1.8,
  loading_docks:1,dock_height_m:1.1,personnel_door:true});
export const facadeSettings = roof => ({...FACADE_DEFAULTS,...roof?.facade});
const EPS = 1e-6;
const distance = (a,b) => Math.hypot(b[0]-a[0],b[1]-a[1]);
const cross = (a,b,c) => (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
function inside(p, polygon) {
  let result = false;
  for (let i=0,j=polygon.length-1;i<polygon.length;j=i++) {
    const a=polygon[i],b=polygon[j];
    if ((a[1]>p[1]) !== (b[1]>p[1]) && p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]) result=!result;
  }
  return result;
}
const pointAt = (s,x,out=0) => [s.a[0]+s.u[0]*x+s.n[0]*out,s.a[1]+s.u[1]*x+s.n[1]*out];
const heightAt = (s,x) => s.heights[0]+(s.heights[1]-s.heights[0])*x/s.length;
const collides = (a,b,gap=.12) => a.x < b.x+b.width+gap && a.x+a.width > b.x-gap && a.z < b.z+b.height+gap && a.z+a.height > b.z-gap;

// The complete canopy footprint must stay outside the building, including concave corners.
function projectionClear(segment, x, width, depth, outline) {
  const rectangle=[pointAt(segment,x,.03),pointAt(segment,x+width,.03),
    pointAt(segment,x+width,depth),pointAt(segment,x,depth)];
  if (rectangle.some(p=>inside(p,outline)) || outline.some(p=>inside(p,rectangle))) return false;
  return !rectangle.some((a,i)=>outline.some((c,j)=>{
    const b=rectangle[(i+1)%4],d=outline[(j+1)%outline.length];
    return cross(a,b,c)*cross(a,b,d)<-EPS && cross(c,d,a)*cross(c,d,b)<-EPS;
  }));
}

export function planFacade(roof, roofGeometry, elevation = () => 0) {
  const settings=facadeSettings(roof), outline=roof.outline ?? [], segments=[], openings=[], columns=[], windows=[];
  const counts={enabled:settings.enabled && !['ground','carport'].includes(roof.type),wall_material:settings.wall_material,
    front_edge:null,windows:0,doors:0,personnel_doors:0,loading_docks:0,canopies:0,columns:0,segments:0};
  if (!counts.enabled || outline.length<3) return {settings,segments,openings,columns,windows,counts};
  const signed=outline.reduce((sum,p,i)=>sum+p[0]*outline[(i+1)%outline.length][1]-outline[(i+1)%outline.length][0]*p[1],0);
  const edges=outline.map((a,i)=>({a,b:outline[(i+1)%outline.length],index:i,length:distance(a,outline[(i+1)%outline.length])}));
  const front=edges[settings.front_edge] ?? edges.reduce((best,e)=>e.length>best.length?e:best,edges[0]);
  counts.front_edge=front.index;
  // Serialized boundary already splits at every ridge and height discontinuity.
  const boundary=roof.type==='pitched' ? roofGeometry?.boundary ?? [] : [...outline,outline[0]].map(p=>[...p,elevation(p)]);
  for (let i=0;i<boundary.length-1;i++) {
    const a=boundary[i],b=boundary[i+1],length=distance(a,b);
    if (length<EPS) continue;
    const edge=edges.find(e=>Math.abs(cross(e.a,e.b,a))/e.length<.021 && Math.abs(cross(e.a,e.b,b))/e.length<.021 &&
      [a,b].every(p=>(p[0]-e.a[0])*(p[0]-e.b[0])+(p[1]-e.a[1])*(p[1]-e.b[1])<=.021));
    if (!edge) continue;
    const u=[(b[0]-a[0])/length,(b[1]-a[1])/length], direction=signed>=0?1:-1;
    segments.push({a:a.slice(0,2),b:b.slice(0,2),length,u,n:[u[1]*direction,-u[0]*direction],edge:edge.index,
      heights:[Math.max(0,roof.height_m+a[2]),Math.max(0,roof.height_m+b[2])],index:segments.length});
  }
  // Allocate openings only to actual exterior segments on the chosen outline edge.
  const slots=[];
  for (const s of segments.filter(s=>s.edge===front.index)) {
    const count=Math.max(1,Math.min(60,Math.floor(s.length/(settings.door_width_m+.8)))), cell=s.length/count;
    for (let i=0;i<count;i++) if (cell>=1.8-EPS) slots.push({segment:s.index,center:(i+.5)*cell,room:cell-.8});
  }
  const types=[];
  for (let i=0;i<Math.max(settings.doors,settings.loading_docks);i++) {
    if (i<settings.doors) types.push('door');
    if (i<settings.loading_docks) types.push('dock');
  }
  if (settings.personnel_door) types.push('personnel');
  const selected=types.slice(0,slots.length), used=new Set();
  selected.forEach((kind,i)=>{
    let index=Math.floor((i+.5)*slots.length/selected.length);
    while (used.has(index)) index=(index+1)%slots.length;
    used.add(index);
    const slot=slots[index],s=segments[slot.segment],width=kind==='personnel'?Math.min(1.05,slot.room):Math.min(settings.door_width_m,slot.room);
    const x=slot.center-width/2,z=kind==='dock'?settings.dock_height_m:0;
    const top=Math.min(heightAt(s,x-.2),heightAt(s,x+width+.2))-.65;
    const height=Math.min(kind==='personnel'?2.25:settings.door_height_m,top-z);
    if (height<(kind==='personnel'?1.95:2) || width<(kind==='personnel' ? .8 : 1)-EPS) return;
    // The dock includes an apron and rubber buffers; all of it must clear the opposite wall.
    if (kind==='dock' && !projectionClear(s,x-.24,width+.48,1.08,outline)) return;
    const opening={kind,segment:s.index,x,z,width,height,canopy_depth:0};
    if (kind!=='personnel' && settings.canopy_depth_m>.1 && x>=.2 && x+width+.2<=s.length) {
      let depth=settings.canopy_depth_m;
      while(depth>=.35 && !projectionClear(s,x-.2,width+.4,depth+.055,outline)) depth-=.1;
      if (depth>=.35) opening.canopy_depth=depth;
    }
    openings.push(opening);
  });
  const renderedBayWidth=Math.max(settings.bay_width_m,segments.reduce((sum,s)=>sum+s.length,0)/800);
  for (const s of segments) {
    const count=Math.max(1,Math.round(s.length/renderedBayWidth)), cell=s.length/count;
    const local=openings.filter(o=>o.segment===s.index);
    const frontSill=Math.max(settings.window_sill_m,...local.map(o=>o.z+o.height+(o.canopy_depth?.65:.3)));
    for (let i=0;i<count;i++) for (let row=0;row<settings.window_rows;row++) {
      const width=Math.min(settings.window_width_m,cell-.65),height=settings.window_height_m;
      const x=(i+.5)*cell-width/2,z=frontSill+row*(height+.45);
      const candidate={kind:'window',segment:s.index,x,z,width,height};
      if (width<.4 || z+height+.3>Math.min(heightAt(s,x),heightAt(s,x+width)) || local.some(o=>collides(candidate,o,.2))) continue;
      windows.push(candidate);
    }
    if (settings.columns) for (let i=0;i<=count;i++) {
      const x=Math.max(.06,Math.min(s.length-.06,i*cell));
      if (local.some(o=>x>o.x-.18 && x<o.x+o.width+.18)) continue;
      columns.push({segment:s.index,x,height:heightAt(s,x)});
    }
  }
  Object.assign(counts,{segments:segments.length,windows:windows.length,columns:columns.length,
    doors:openings.filter(o=>o.kind==='door').length,personnel_doors:openings.filter(o=>o.kind==='personnel').length,
    loading_docks:openings.filter(o=>o.kind==='dock').length,canopies:openings.filter(o=>o.canopy_depth>0).length});
  return {settings,segments,openings,columns,windows,counts};
}

export function createFacade(T, data, roofGeometry) {
  const plan=planFacade(data.roof,roofGeometry,data.elevation),{settings,segments}=plan, group=new T.Group();
  group.name='factory-facade'; group.userData.facade=plan.counts;
  if (!plan.counts.enabled) return {group,stats:()=>({...plan.counts})};
  const buffers=new Map(),lines=new Map();
  // Decorative sampling stays bounded even for very large site imports.
  const wallArea=segments.reduce((sum,s)=>sum+s.length*Math.max(...s.heights),0);
  const detailScale=Math.max(1,Math.sqrt(wallArea/2400),segments.reduce((sum,s)=>sum+s.length,0)/4000,
    segments.reduce((sum,s)=>sum+Math.max(...s.heights),0)/1500);
  const colors={wall:settings.wall_color,trim:settings.trim_color,base:settings.base_color,door:settings.door_color,
    glass:'#315b70',reflection:'#b4d3dd',shadow:'#26353c',yellow:'#e7b43e',paving:'#9fa5a7'};
  const world=([x,y,z])=>[x-data.center[0],z,-y+data.center[1]];
  function point(s,x,z,out=.025) {return [...pointAt(s,x,out),z];}
  function quad(key,points) {
    if (!buffers.has(key)) buffers.set(key,[]);
    const target=buffers.get(key),p=points.map(world);
    for (const i of [0,1,2,0,2,3]) target.push(...p[i]);
  }
  function line(key,a,b) {
    if (!lines.has(key)) lines.set(key,[]);
    lines.get(key).push(...world(a),...world(b));
  }
  function rect(key,s,x,z,width,height,out=.04) {
    quad(key,[point(s,x,z,out),point(s,x+width,z,out),point(s,x+width,z+height,out),point(s,x,z+height,out)]);
  }
  function box(key,s,x,z,width,height,depth,out=.035) {
    const front=[point(s,x,z,out+depth),point(s,x+width,z,out+depth),point(s,x+width,z+height,out+depth),point(s,x,z+height,out+depth)];
    const back=[point(s,x,z,out),point(s,x+width,z,out),point(s,x+width,z+height,out),point(s,x,z+height,out)];
    quad(key,front);quad(key,[back[3],back[2],back[1],back[0]]);
    for(let i=0;i<4;i++) {const j=(i+1)%4;quad(key,[back[i],back[j],front[j],front[i]]);}
  }
  function frame(s,o,out=.105) {
    box('trim',s,o.x-.09,o.z,.09,o.height+.12,.06,out);
    box('trim',s,o.x+o.width,o.z,.09,o.height+.12,.06,out);
    box('trim',s,o.x-.09,o.z+o.height,o.width+.18,.12,.06,out);
  }
  for(const s of segments) {
    quad('wall',[point(s,0,0),point(s,s.length,0),point(s,s.length,s.heights[1]),point(s,0,s.heights[0])]);
    const base=Math.min(settings.base_height_m,...s.heights);
    if(base>0) rect('base',s,0,0,s.length,base,.04);
    quad('trim',[point(s,0,s.heights[0]-.16,.065),point(s,s.length,s.heights[1]-.16,.065),
      point(s,s.length,s.heights[1],.065),point(s,0,s.heights[0],.065)]);
    if(s.heights[0]===s.heights[1] && s.heights[0]>.5) {
      box('trim',s,0,s.heights[0]-.16,s.length,.16,.075,.04);
      if(settings.wall_material==='brick' && s.heights[0]>1.2) {
        box('base',s,0,s.heights[0]-.30,s.length,.08,.055,.035);
        for(let x=.25*detailScale;x<s.length-.2;x+=.5*detailScale) {
          box('trim',s,x,s.heights[0]-.42,.14,.10,.05,.035);
        }
      }
    }
    if(settings.wall_material==='metal') for(let x=.32*detailScale;x<s.length;x+=.42*detailScale) {
      line('base',point(s,x,base,.03),point(s,x,heightAt(s,x)-.16,.03));
    }
    if(settings.wall_material!=='metal') {
      const rise=(settings.wall_material==='brick' ? .24 : 1.4)*detailScale, run=(settings.wall_material==='brick' ? .65 : 3)*detailScale;
      for(let z=base+rise,row=0;z<Math.max(...s.heights)-.16;z+=rise,row++) {
        const range=s.heights[0]===s.heights[1] ? [0,s.length] : s.heights[0]<s.heights[1] ?
          [Math.max(0,(z+.16-s.heights[0])*s.length/(s.heights[1]-s.heights[0])),s.length] :
          [0,Math.min(s.length,(s.heights[0]-z-.16)*s.length/(s.heights[0]-s.heights[1]))];
        if(range[1]<=range[0]) continue;
        line('base',point(s,range[0],z,.03),point(s,range[1],z,.03));
        for(let x=run*(row%2?.5:1);x<s.length;x+=run) {
          if(z<heightAt(s,x)-.16) line('base',point(s,x,Math.max(base,z-rise),.03),point(s,x,z,.03));
        }
      }
    }
  }
  for(const c of plan.columns) box('trim',segments[c.segment],c.x-.07,0,.14,Math.max(0,c.height-.16),.07,.045);
  for(const o of plan.windows) {
    const s=segments[o.segment];
    rect('shadow',s,o.x-.07,o.z-.07,o.width+.14,o.height+.14,.075);
    rect('glass',s,o.x,o.z,o.width,o.height,.09);frame(s,o,.095);
    box('trim',s,o.x-.09,o.z-.07,o.width+.18,.08,.07,.09);
    const panes=Math.max(1,Math.ceil(o.width/1.1));
    for(let i=1;i<panes;i++) box('trim',s,o.x+o.width*i/panes-.025,o.z,.05,o.height,.025,.1);
    if(o.height>=.7) box('trim',s,o.x,o.z+o.height*.64,o.width,.04,.025,.1);
    if(settings.wall_material==='brick') {
      for(let x=o.x+.22;x<o.x+o.width-.15;x+=.28) line('trim',point(s,x,o.z+.04,.112),point(s,x,o.z+o.height-.04,.112));
      line('trim',point(s,o.x+.04,o.z+o.height*.32,.112),point(s,o.x+o.width-.04,o.z+o.height*.32,.112));
    }
    rect('reflection',s,o.x+.06,o.z+o.height*.72,o.width-.12,.035,.115);
    rect('reflection',s,o.x+.1,o.z+o.height*.26,Math.max(.12,o.width*.55),.025,.115);
  }
  for(const o of plan.openings) {
    const s=segments[o.segment];
    rect('shadow',s,o.x-.12,o.z,o.width+.24,o.height+.18,.065);
    rect('door',s,o.x,o.z,o.width,o.height,.09);frame(s,o);
    if(o.kind==='personnel') {
      rect('glass',s,o.x+.16,o.z+1.35,o.width-.32,.57,.115);
      box('reflection',s,o.x+o.width-.2,.95,.055,.25,.04,.13);
      box('paving',s,o.x-.15,0,o.width+.3,.06,.75,.03);
    } else {
      for(let z=o.z+.17;z<o.z+o.height;z+=.18) line('trim',point(s,o.x,z,.115),point(s,o.x+o.width,z,.115));
      box('trim',s,o.x,o.z,o.width,.1,.08,.085);
      if(o.kind==='door') {
        box('paving',s,o.x-.2,0,o.width+.4,.05,1.2,.03);
        for(const bx of [o.x-.22,o.x+o.width+.1]) {
          box('yellow',s,bx,0,.11,.82,.11,.22);
          box('shadow',s,bx-.005,.52,.12,.12,.12,.215);
        }
      }
      if(o.kind==='dock') {
        box('paving',s,o.x-.24,0,o.width+.48,o.z,.9,.03);
        box('shadow',s,o.x+.12,o.z-.55,.16,.55,.13,.94);
        box('shadow',s,o.x+o.width-.28,o.z-.55,.16,.55,.13,.94);
        line('trim',point(s,o.x+.18,o.z+.01,.08),point(s,o.x+o.width-.18,o.z+.01,.08));
        line('trim',point(s,o.x+.18,o.z+.01,.84),point(s,o.x+o.width-.18,o.z+.01,.84));
        for(let x=o.x-.2;x<o.x+o.width+.2;x+=.42) {
          const w=Math.min(.21,o.x+o.width+.24-x);
          quad('yellow',[point(s,x,.14,.941),point(s,x+w,.14,.941),point(s,x+w+.12,.38,.941),point(s,x+.12,.38,.941)]);
        }
      }
      if(o.canopy_depth>0) {
        const z=o.z+o.height+.27, d=o.canopy_depth;
        box('trim',s,o.x-.2,z,o.width+.4,.1,d,.055);
        box('door',s,o.x-.21,z-.02,o.width+.42,.13,.05,d+.02);
        for(const x of [o.x+.18,o.x+o.width-.18]) {
          box('trim',s,x-.05,z+.52,.1,.14,.04,.06);
          line('trim',point(s,x,z+.6,.09),point(s,x,z+.1,d*.86));
          line('trim',point(s,x,z-.65,.12),point(s,x,z-.02,d*.86));
          line('trim',point(s,x,z-.61,.12),point(s,x,z+.02,d*.86));
        }
      }
    }
  }
  for(const [key,coordinates] of buffers) {
    const geometry=new T.BufferGeometry();geometry.setAttribute('position',new T.Float32BufferAttribute(coordinates,3));geometry.computeVertexNormals();geometry.computeBoundingSphere();
    const material=new T.MeshStandardMaterial({color:new T.Color(colors[key]).convertSRGBToLinear(),side:T.DoubleSide,
      roughness:key==='glass'?.22:.76,metalness:key==='glass'?.28:.05});
    const object=new T.Mesh(geometry,material);object.castShadow=true;object.receiveShadow=true;group.add(object);
  }
  for(const [key,coordinates] of lines) {
    const geometry=new T.BufferGeometry();geometry.setAttribute('position',new T.Float32BufferAttribute(coordinates,3));
    group.add(new T.LineSegments(geometry,new T.LineBasicMaterial({color:new T.Color(colors[key]).convertSRGBToLinear()})));
  }
  return {group,stats:()=>({...plan.counts})};
}
