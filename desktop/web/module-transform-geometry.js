// Model coordinates are metres: X east, Y north, Z relative to the roof datum.
const RAD=Math.PI/180;
const dot=(a,b)=>a.reduce((sum,value,i)=>sum+value*b[i],0);
const subtract=(a,b)=>a.map((value,i)=>value-b[i]);
const scale=(a,value)=>a.map(component=>component*value);
const add=(a,b)=>a.map((value,i)=>value+b[i]);
const unit=a=>scale(a,1/Math.hypot(...a));
export const moduleSurfaceId=module=>/^P(\d+)-/.exec(module.id)?.[1] ?? 'roof';
export function moduleSurface(module,roof) {
  return roof.type==='pitched' ? roof.planes?.find(plane=>String(plane.id)===moduleSurfaceId(module)) : roof;
}
export function surfaceFrame(surface,flat=false) {
  if (flat) return {right:[1,0,0],uphill:[0,1,0],normal:[0,0,1]};
  const beta=surface.slope_deg*RAD,bearing=surface.slope_azimuth_deg*RAD;
  return {right:[-Math.cos(bearing),Math.sin(bearing),0],
    uphill:[-Math.sin(bearing)*Math.cos(beta),-Math.cos(bearing)*Math.cos(beta),Math.sin(beta)],
    normal:[Math.sin(beta)*Math.sin(bearing),Math.sin(beta)*Math.cos(bearing),Math.cos(beta)]};
}
export function surfaceElevation(surface,point,flat=false) {
  if (flat) return 0;
  const bearing=surface.slope_azimuth_deg*RAD,station=p=>-p[0]*Math.sin(bearing)-p[1]*Math.cos(bearing);
  return (surface.offset_m ?? 0)+(station(point)-Math.min(...surface.outline.map(station)))*Math.tan(surface.slope_deg*RAD);
}
// Split lock annotations at every roof boundary. Each segment belongs to one
// physical face, so a height step never becomes a fictitious sloping connector.
export function lockedRegionSegments(roof,polygon) {
  const cross=(a,b)=>a[0]*b[1]-a[1]*b[0],inside=(point,outline)=>{
    let found=false;
    for(let i=0,j=outline.length-1;i<outline.length;j=i++) {
      const a=outline[j],b=outline[i],edge=subtract(b,a),relative=subtract(point,a);
      if(Math.abs(cross(edge,relative))<1e-8 && dot(relative,edge)>=-1e-8 && dot(relative,edge)<=dot(edge,edge)+1e-8)return true;
      if((a[1]>point[1])!==(b[1]>point[1]) && point[0]<(b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0])found=!found;
    }
    return found;
  };
  if(!Array.isArray(polygon)||polygon.length<3)return [];
  const planes=roof.type==='pitched'?[...(roof.planes ?? [])].sort((a,b)=>a.id-b.id):[roof],segments=[];
  for(let i=0;i<polygon.length;i++) {
    const a=polygon[i],b=polygon[(i+1)%polygon.length],direction=subtract(b,a),cuts=[0,1];
    if(Math.hypot(...direction)<1e-8)continue;
    for(const plane of planes)for(let j=0;j<plane.outline.length;j++) {
      const c=plane.outline[j],d=plane.outline[(j+1)%plane.outline.length],edge=subtract(d,c),offset=subtract(c,a),denom=cross(direction,edge);
      if(Math.abs(denom)<1e-10)continue;
      const t=cross(offset,edge)/denom,u=cross(offset,direction)/denom;
      if(t>1e-8&&t<1-1e-8&&u>=-1e-8&&u<=1+1e-8)cuts.push(t);
    }
    const ordered=[...new Set(cuts.map(t=>Math.round(t*1e10)/1e10))].sort((a,b)=>a-b);
    for(let j=1;j<ordered.length;j++) {
      const from=add(a,scale(direction,ordered[j-1])),to=add(a,scale(direction,ordered[j]));
      const plane=planes.find(surface=>inside(add(from,to).map(v=>v/2),surface.outline));
      if(!plane)continue;
      segments.push([from,to].map(point=>[...point,surfaceElevation(plane,point,roof.type==='flat')]));
    }
  }
  return segments;
}
export function transformModuleGeometry(module,roof,operation,spec) {
  const surface=moduleSurface(module,roof),flush=roof.type==='metal'||roof.type==='pitched';
  if (!surface || ![spec?.length_m,spec?.width_m,spec?.lower_edge_m].every(Number.isFinite)) return null;
  const length=module.orientation==='portrait'?spec.length_m:spec.width_m;
  const width=module.orientation==='portrait'?spec.width_m:spec.length_m;
  const rotation=operation.mode==='rotate' ? operation.angle_deg ?? 0 : 0;
  const tilt=flush?surface.slope_deg:module.tilt;
  const azimuth=flush?surface.slope_azimuth_deg:((module.azimuth+rotation)%360+360)%360;
  let {right,uphill}=surfaceFrame({slope_deg:tilt,slope_azimuth_deg:azimuth});
  if (flush) {
    const axis=subtract(module.corners[1],module.corners[0]);
    const theta=Math.atan2(-dot(axis,uphill),dot(axis,right))+rotation*RAD;
    [right,uphill]=[add(scale(right,Math.cos(theta)),scale(uphill,-Math.sin(theta))),
      add(scale(right,Math.sin(theta)),scale(uphill,Math.cos(theta)))];
  }
  const center=[module.center[0]+(operation.mode==='move'?operation.dx_m ?? 0:0),
    module.center[1]+(operation.mode==='move'?operation.dy_m ?? 0:0),0];
  center[2]=flush?surfaceElevation(surface,center)+spec.lower_edge_m:spec.lower_edge_m+length*Math.sin(tilt*RAD)/2;
  const corners=[[-1,-1],[1,-1],[1,1],[-1,1]].map(([x,y])=>add(center,add(scale(right,x*width/2),scale(uphill,y*length/2))));
  return {...module,center,corners,tilt,azimuth};
}
export function normalizeTurn(degrees) {
  const value=((degrees+180)%360+360)%360-180;
  return Math.abs(value)<1e-10?0:value;
}
export function snapModuleAngle(degrees,{enabled=true,angleDeg=15}={},alt=false) {
  let angle=normalizeTurn(degrees);
  const active=enabled&&!alt&&Number.isFinite(angleDeg)&&angleDeg>0&&angleDeg<=180;
  if (active) angle=normalizeTurn(Math.round(angle/angleDeg)*angleDeg);
  return {angle_deg:angle,snap:{applied:active,kind:active?'angle':'none'}};
}
// Grid snaps the grabbed module centre in the site XY system. Nearby alignment
// uses the actual panel-edge axes and true roof-plane distances on sloped roofs.
export function snapModuleMove(anchor,modules,selectedIds,roof,spec,delta,settings={},alt=false) {
  const {enabled=true,gridM=.1,align=true,toleranceM=.12}=settings;
  let dx=delta.dx_m,dy=delta.dy_m;
  const result=()=>({dx_m:dx,dy_m:dy,snap:{applied:false,kind:'none'},guides:[]});
  if (!enabled||alt) return result();
  let kind='none';
  if (Number.isFinite(gridM)&&gridM>0) {
    dx=Math.round((anchor.center[0]+dx)/gridM)*gridM-anchor.center[0];
    dy=Math.round((anchor.center[1]+dy)/gridM)*gridM-anchor.center[1];
    kind='grid';
  }
  const answer=result();answer.snap={applied:kind!=='none',kind};
  if (!align) return answer;
  const moving=transformModuleGeometry(anchor,roof,{mode:'move',dx_m:dx,dy_m:dy},spec);
  if (!moving) return answer;
  const flat=roof.type==='flat',surface=moduleSurface(anchor,roof),base=surfaceFrame(surface,flat);
  const project=p=>[dot(p,base.right),dot(p,base.uphill)];
  const points=moving.corners.map(project),center=project(moving.center);
  const axis=unit(subtract(points[1],points[0])),cross=[-axis[1],axis[0]];
  const bounds=rows=>[axis,cross].map(a=>{const values=rows.map(p=>dot(p,a));return [Math.min(...values),Math.max(...values)];});
  const own=bounds(points),centerAlong=[dot(center,axis),dot(center,cross)];
  const excluded=new Set(selectedIds),best=[null,null],tolerance=Math.max(.001,Math.min(.5,toleranceM));
  const consider=(index,amount,type,target,rank)=>{
    if (Math.abs(amount)>tolerance) return;
    const score=Math.abs(amount)+rank*1e-5;
    if (!best[index]||score<best[index].score) best[index]={amount,type,target,score};
  };
  for (const neighbor of modules) {
    if (excluded.has(neighbor.id)||moduleSurfaceId(neighbor)!==moduleSurfaceId(anchor)) continue;
    const target=neighbor.corners.map(project),targetCenter=project(neighbor.center),other=bounds(target);
    if (Math.hypot(...subtract(targetCenter,center))>Math.max(spec.length_m,spec.width_m)*3+tolerance) continue;
    const edge=unit(subtract(target[1],target[0])),parallel=Math.abs(dot(edge,axis))>1-1e-5||Math.abs(dot(edge,cross))>1-1e-5;
    for (let index=0;index<2;index++) {
      consider(index,dot(targetCenter,index===0?axis:cross)-centerAlong[index],'center',neighbor,2);
      if (!parallel) continue;
      for (const side of [0,1]) consider(index,other[index][side]-own[index][side],'edge',neighbor,1);
      consider(index,other[index][0]-spec.gap_m-own[index][1],'gap',neighbor,0);
      consider(index,other[index][1]+spec.gap_m-own[index][0],'gap',neighbor,0);
    }
  }
  if (!best.some(Boolean)) return answer;
  const correction=add(scale(axis,best[0]?.amount ?? 0),scale(cross,best[1]?.amount ?? 0));
  const world=add(scale(base.right,correction[0]),scale(base.uphill,correction[1]));
  dx+=world[0];dy+=world[1];
  const kinds=best.filter(Boolean).map(value=>value.type),chosen=kinds.includes('gap')?'gap':kinds.includes('edge')?'edge':'center';
  return {dx_m:dx,dy_m:dy,snap:{applied:true,kind:chosen,targetIds:[...new Set(best.filter(Boolean).map(value=>value.target.id))]},
    guides:best.filter(Boolean).map(value=>({from:transformModuleGeometry(anchor,roof,{mode:'move',dx_m:dx,dy_m:dy},spec).center,to:value.target.center}))};
}
